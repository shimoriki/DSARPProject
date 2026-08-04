"""Mine REAL historical refactorings (RefactoringMiner) + align with smells -> real labels.

Uses the downloaded RefactoringMiner (tools/RefactoringMiner-*/). For each repo:
  deepen git history to --depth commits -> run RefactoringMiner (-a branch)
  -> parse events -> keep ARCHITECTURAL refactoring types -> align with the repo's
  structural smells (component overlap + type plausibility) -> write REAL alignments.

Cassandra is blocked (unseen). Real historical labels are stronger than graph weak labels,
so they diversify the training signal (fixes the degenerate all-graph-delta labelling).

Usage:
  python scripts/mine_and_align_refactorings.py --repos apache/commons-cli,apache/commons-lang --depth 500 --train
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import time
from pathlib import Path

import _bootstrap  # noqa: F401
from dsarp.alignment.aligner import SmellRefactoringAligner
from dsarp.alignment.weak import GraphWeakAligner
from dsarp.config import load_config
from dsarp.dataset.builder import DatasetBuilder
from dsarp.inference.unseen import prepare_evidence
from dsarp.mining.refactoring_miner import (RefactoringMinerAdapter,
                                            ARCHITECTURAL_REFACTORINGS, is_architectural)
from dsarp.repositories.manager import RepositoryManager, slug_to_dirname
from dsarp.schemas import EvidenceCase
from dsarp.splits.manager import SplitManager
from dsarp.training.ranker_trainer import RankerTrainer
from dsarp.util import read_json, write_json

ARCH_TYPES = ARCHITECTURAL_REFACTORINGS  # strict architectural-only (code-level excluded)


def _force_rmtree(path: Path) -> None:
    """Windows-safe recursive delete: clear read-only bit on locked .git pack files."""
    import os
    import stat

    def onerror(func, p, exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass
    if Path(path).exists():
        shutil.rmtree(path, onerror=onerror)


def _rm_dir() -> Path:
    root = Path(__file__).resolve().parent.parent / "tools"
    cands = sorted(p for p in root.glob("RefactoringMiner-*") if p.is_dir())  # exclude the .zip
    return cands[-1] if cands else root / "RefactoringMiner-3.1.4"


def _win(path: Path) -> str:
    """Absolute Windows-style path (forward slashes) the JVM accepts."""
    return str(Path(path).resolve()).replace("\\", "/")


def _git_bounded(cmd, timeout: int):
    """Run a git command with a HARD timeout that kills the whole process tree.

    Root-cause fix for the multi-hour hangs: `subprocess.run(timeout=...)` kills only
    git.exe, but git spawns git-remote-https / git-index-pack grandchildren that inherit
    the stdout/stderr pipe. On timeout, communicate() then BLOCKS until those orphans
    finish (observed: a 258-commit deepen ran ~7 hours). Here we `taskkill /F /T` the
    whole tree so the pipe closes immediately. Returns (returncode, stderr). 124 = timeout.
    """
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        _out, err = p.communicate(timeout=timeout)
        return p.returncode, err
    except subprocess.TimeoutExpired:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                           capture_output=True, timeout=30)
        except Exception:
            p.kill()
        try:
            p.communicate(timeout=10)
        except Exception:
            pass
        return 124, "timeout"


def run_refactoring_miner(repo_path: Path, branch: str, out_json: Path,
                          max_commits: int = 0) -> int:
    rmdir = _rm_dir()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_json.with_name(out_json.stem + ".partial.json")  # atomic: write tmp, rename on success
    if tmp.exists():
        tmp.unlink()
    if max_commits and max_commits > 0:
        # BOUND RM to the last N commits (-bc start end) so big repos finish fast.
        total = int(subprocess.run(["git", "-C", str(repo_path), "rev-list", "--count", "HEAD"],
                                    capture_output=True, text=True).stdout.strip() or 0)
        n = min(max_commits, max(1, total - 1))
        start = subprocess.run(["git", "-C", str(repo_path), "rev-parse", f"HEAD~{n}"],
                               capture_output=True, text=True).stdout.strip()
        head = subprocess.run(["git", "-C", str(repo_path), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        cmd = ["java", "-Xmx6g", "-cp", "lib/*", "org.refactoringminer.RefactoringMiner",
               "-bc", _win(repo_path), start, head, "-json", _win(tmp)] if start else \
              ["java", "-Xmx6g", "-cp", "lib/*", "org.refactoringminer.RefactoringMiner",
               "-a", _win(repo_path), branch, "-json", _win(tmp)]
    else:
        cmd = ["java", "-Xmx6g", "-cp", "lib/*", "org.refactoringminer.RefactoringMiner",
               "-a", _win(repo_path), branch, "-json", _win(tmp)]
    try:
        # bounded per-repo so a giant repo can't run for an hour (caller resilient to timeout)
        proc = subprocess.run(cmd, cwd=str(rmdir), capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        if tmp.exists():
            tmp.unlink()  # never leave a truncated cache file
        return 124
    if proc.returncode == 0 and tmp.exists():
        tmp.replace(out_json)  # atomic swap into place
    elif tmp.exists():
        tmp.unlink()
    return proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos", required=True, help="comma-separated org/name slugs")
    ap.add_argument("--depth", type=int, default=500, help="commits of history to mine")
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--skip-mine", action="store_true",
                    help="reuse existing RefactoringMiner json (skip slow git-deepen + RM)")
    ap.add_argument("--clone-timeout", type=int, default=1200,
                    help="seconds per fresh clone before skipping a too-large repo")
    ap.add_argument("--max-commits", type=int, default=0,
                    help="bound RM to the last N commits (-bc) so big repos finish fast; 0=whole branch")
    args = ap.parse_args()

    cfg = load_config("local")
    sm = SplitManager()
    rm = RepositoryManager(cfg.data_dir)
    adapter = RefactoringMinerAdapter()
    real_aligner = SmellRefactoringAligner()
    weak_aligner = GraphWeakAligner()
    builder = DatasetBuilder(cfg.data_dir / "training")

    out_ds = cfg.data_dir / "training" / "real_labeled_candidates.jsonl"
    if out_ds.exists():
        out_ds.unlink()

    all_rows, summary = [], []
    for slug in [s.strip() for s in args.repos.split(",") if s.strip()]:
        pid = slug_to_dirname(slug)
        if not sm.is_training_allowed(pid):
            print(f"[rm] SKIP {pid}: blocked (unseen/leakage)"); continue
        dest = rm.path_for(pid)
        t0 = time.time()
        out_json = cfg.data_dir / "raw" / "refactoringminer" / f"{pid}.json"
        rc = 0
        if args.skip_mine and out_json.exists():
            print(f"[rm] {pid}: reusing cached RefactoringMiner json (skip mine)", flush=True)
        else:
            cur = 0
            if (dest / ".git").exists():
                cur = int(subprocess.run(["git", "-C", str(dest), "rev-list", "--count", "HEAD"],
                                         capture_output=True, text=True).stdout.strip() or 0)
            # NEVER deepen an existing clone. `git fetch --depth=N` on a partial clone
            # re-negotiates the whole history and is the source of the multi-hour hangs
            # (observed: tika 521->1200 sat silent for 20+ minutes and produced nothing,
            # even with a bounded timeout). A fresh shallow clone to the target depth is
            # bounded, tree-killable, and in practice much faster.
            if cur >= args.depth:
                print(f"[rm] {pid}: already has {cur} commits (>= {args.depth}); reusing",
                      flush=True)
            elif args.depth > 1:
                _force_rmtree(dest)  # Windows-safe (clears read-only .git packs)
                print(f"[rm] fresh clone {slug} --depth {args.depth} ...", flush=True)
                # tree-killing clone (git grandchildren can't orphan and hang for hours)
                rc_c, err_c = _git_bounded(["git", "clone", "--depth", str(args.depth),
                                            f"https://github.com/{slug}.git", str(dest)],
                                           timeout=args.clone_timeout)
                if rc_c == 124:
                    print(f"[rm] clone timeout for {pid} (repo too large); skipping", flush=True)
                elif rc_c != 0:
                    tail = (err_c.strip().splitlines() or ["?"])[-1][:120]
                    print(f"[rm] clone failed {pid}: {tail}", flush=True)
            if not (dest.exists() and any(dest.rglob("*.java"))):
                print(f"[rm] SKIP {pid}: no source after clone (too slow/failed)", flush=True)
                continue
            branch = subprocess.run(["git", "-C", str(dest), "rev-parse", "--abbrev-ref", "HEAD"],
                                    capture_output=True, text=True).stdout.strip() or "master"
            rc = run_refactoring_miner(dest, branch, out_json, max_commits=args.max_commits)

        # 1) parse mined refactorings (architectural only)
        events = adapter.import_events(out_json) if out_json.exists() else []
        arch = [e for e in events if e.refactoring_type in ARCH_TYPES]
        write_json(cfg.data_dir / "refactoring_events" / f"{pid}.json", [e.to_dict() for e in events])

        # 2) structural smells for the same repo
        prepare_evidence(cfg, pid, repo_path=dest)
        case = EvidenceCase(**read_json(cfg.data_dir / "normalized" / f"{pid}.json"))

        # 3) REAL alignments (historical) + weak (graph) fallback
        real_aligns = real_aligner.align(case.smells, arch)
        weak_aligns = weak_aligner.align(case.smells, case.dependency_graph)
        aligns = real_aligns + weak_aligns
        write_json(cfg.data_dir / "aligned_examples" / f"{pid}.json", [a.__dict__ for a in aligns])

        rows = []
        for smell in case.smells:
            rows += builder.build_ranker_rows(pid, "train", smell, case.dependency_graph, aligns)
        for r in rows:
            builder.write_candidates([r], "real_labeled_candidates.jsonl")
        all_rows += rows
        real_pos = sum(1 for a in real_aligns if a.alignment_confidence >= 0.5)
        line = (f"[rm] {pid}: commits~{args.depth} refactorings={len(events)} "
                f"architectural={len(arch)} real_aligns={len(real_aligns)}(pos~{real_pos}) "
                f"smells={len(case.smells)} rows={len(rows)} ({time.time()-t0:.0f}s) rc={rc}")
        print(line, flush=True)
        summary.append(line)

    stats = builder.stats(all_rows) if all_rows else {"examples": 0}
    print(f"[rm] TOTAL rows={stats.get('examples')} positives={stats.get('positive')} "
          f"repos={stats.get('repositories')} -> {out_ds}", flush=True)

    if args.train and all_rows and stats.get("repositories", 0) >= 2:
        trainer = RankerTrainer(cfg.data_dir / "models")
        res = trainer.train(out_ds)
        m = res["metadata"]
        print(f"[rm] ranker: {m['backend']} on {m['training_example_count']} rows "
              f"({len(m['training_repositories'])} repos), train_score={m['train_score']}")
        loro = trainer.leave_one_repo_out(out_ds)
        print(f"[rm] LORO mean_validation_score={loro['mean_validation_score']} "
              f"(real labels => expect < 1.0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
