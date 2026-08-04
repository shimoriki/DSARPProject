"""Build a REAL multi-repository training dataset from real repos (no JVM tools).

For each repo (org/name slug or local path):
  shallow-clone if needed -> source index -> import-graph -> real graph smells
  -> deterministic candidates -> WEAK labels from real graph structure
  -> masked, repo-independent training rows.

RefactoringMiner/Arcan/Designite are NOT required. Labels are weak supervision from
the real dependency graph (never fabricated history). Cassandra is blocked.

Usage:
  python scripts/build_real_repo_dataset.py --repos apache/commons-cli,apache/commons-io [--train]
  python scripts/build_real_repo_dataset.py --paths C:/x/repoA,C:/y/repoB
"""
from __future__ import annotations

import argparse
from pathlib import Path

import time
import traceback

import _bootstrap  # noqa: F401
from dsarp.alignment.weak import GraphWeakAligner
from dsarp.config import load_config, load_repo_entries
from dsarp.dataset.builder import DatasetBuilder
from dsarp.inference.unseen import prepare_evidence
from dsarp.repositories.manager import RepositoryManager, slug_to_dirname
from dsarp.schemas import EvidenceCase
from dsarp.splits.manager import SplitManager
from dsarp.training.ranker_trainer import RankerTrainer
from dsarp.util import read_json, write_json

OUT = "real_multi_repo_train_candidates.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos", default="", help="comma-separated org/name slugs")
    ap.add_argument("--paths", default="", help="comma-separated local repo paths")
    ap.add_argument("--config", default="", help="split kind (e.g. train) — clones the whole list")
    ap.add_argument("--train", action="store_true", help="train ranker + LORO after building")
    args = ap.parse_args()

    cfg = load_config("local")
    sm = SplitManager()
    sm.assert_no_leakage()
    rm = RepositoryManager(cfg.data_dir)
    aligner = GraphWeakAligner()
    builder = DatasetBuilder(cfg.data_dir / "training")

    slugs = [s.strip() for s in args.repos.split(",") if s.strip()]
    if args.config:
        slugs += [e["repo_url"].split("github.com/")[-1] for e in load_repo_entries(args.config)
                  if e.get("repo_url")]

    targets = []  # (project_id, repo_path)
    for slug in slugs:
        pid = slug_to_dirname(slug)
        if not sm.is_training_allowed(pid):
            print(f"[real] SKIP {pid}: blocked from training (unseen/leakage)")
            continue
        dest = rm.path_for(pid)
        has_java = dest.exists() and any(dest.rglob("*.java"))
        if not has_java:
            print(f"[real] cloning {slug} (shallow) ...", flush=True)
            st = rm.clone(slug, depth=1)
            if not (dest.exists() and any(dest.rglob("*.java"))):
                print(f"[real] SKIP {pid}: clone produced no .java ({st.note})", flush=True)
                continue
        targets.append((pid, rm.path_for(pid)))
    for p in [s.strip() for s in args.paths.split(",") if s.strip()]:
        pid = Path(p).name
        targets.append((pid, Path(p)))

    out_path = cfg.data_dir / "training" / OUT
    if out_path.exists():
        out_path.unlink()

    all_rows = []
    for pid, path in targets:
        t0 = time.time()
        try:
            prep = prepare_evidence(cfg, pid, repo_path=path)
            case = EvidenceCase(**read_json(cfg.data_dir / "normalized" / f"{pid}.json"))
            aligns = aligner.align(case.smells, case.dependency_graph)
            write_json(cfg.data_dir / "aligned_examples" / f"{pid}.json",
                       [a.__dict__ for a in aligns])
            rows = []
            for smell in case.smells:
                rows += builder.build_ranker_rows(pid, "train", smell, case.dependency_graph, aligns)
            for r in rows:
                builder.write_candidates([r], OUT)
            all_rows += rows
            pos = sum(r["label"] for r in rows)
            print(f"[real] {pid}: files={prep['source_files']} smells={prep['smells']} "
                  f"rows={len(rows)} positives={pos} ({time.time()-t0:.0f}s)", flush=True)
        except Exception as exc:  # resilient: one bad repo must not abort the run
            print(f"[real] ERROR {pid}: {exc} ({traceback.format_exc().splitlines()[-1]})",
                  flush=True)

    stats = builder.stats(all_rows) if all_rows else {"examples": 0}
    print(f"[real] TOTAL rows={stats.get('examples')} positives={stats.get('positive')} "
          f"repos={stats.get('repositories')} -> {out_path}")

    if args.train and all_rows:
        trainer = RankerTrainer(cfg.data_dir / "models")
        res = trainer.train(out_path)
        m = res["metadata"]
        print(f"[real] ranker: {m['backend']} on {m['training_example_count']} real rows "
              f"({len(m['training_repositories'])} repos), train_score={m['train_score']}")
        if stats.get("repositories", 0) >= 2:
            loro = trainer.leave_one_repo_out(out_path)
            print(f"[real] LORO mean_validation_score={loro['mean_validation_score']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
