"""Plan edge-eliminating refactorings, apply them, and judge them with the bytecode oracle.

This is the experiment behind the project's only verified numbers: 18 planned moves applied
across pdfbox, log4j2 and tika, 18 built, 18 removing their targeted package edge, 14 accepted
once tests were compared against each repository's own baseline.

The order of work is the order of cost, so a rejection is cheap:

    plan        exact effect arithmetic on the class-level graph  -- no build
    warn        names the compiler cannot see (poms, service files, string literals)
    apply       Spoon
    post        the old name must be gone from the tree           -- no build
    build       reactor test-compile, so stranded tests count as broken
    oracle      ArchUnit edges, cross-read by jdeps
    tests       the project's own suite against its own baseline  -- the only accepting gate

Nothing here decides a verdict itself; `dsarp.verification.gates` owns the rules.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..refactoring import spoon_plan
from ..refactoring.move_planner import plan_moves
from ..refactoring.strategies import SourceFacts
from ..tools import archunit_runner as au
from ..tools import jdeps_runner
from ..tools.arcan_runner import compile_repo, modules_for, run_tests
from ..tools.spoon_runner import apply_edits, module_classpath
from ..verification import gates
from ..verification.effect_checker import _copy_repo


def _log(msg: str, quiet: bool = False) -> None:
    if not quiet:
        print(msg, flush=True)


def baseline(repo: Path, out_dir: Path, quiet: bool = False) -> Dict[str, Any]:
    """Compile the repository and snapshot its package edges, cached.

    Cached because the snapshot is of unmodified source: re-deriving it per candidate cost
    minutes and could only ever produce the same answer.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = out_dir / "before.json"
    if cache.exists():
        snap = json.loads(cache.read_text(encoding="utf-8"))
        if snap.get("ok"):
            return snap
    c = compile_repo(repo, log_path=out_dir / "baseline_compile.log")
    if not c.get("ok"):
        raise RuntimeError("baseline does not compile: %s" % (c.get("javac_errors") or c["status"]))
    snap = au.cycles(repo, log_path=out_dir / "baseline_cycles.log")
    if not snap.get("ok"):
        raise RuntimeError("oracle blind on the baseline: %s" % snap.get("why"))
    cache.write_text(json.dumps(snap, indent=1), encoding="utf-8")
    _log("[baseline] %s packages, %s classes, %s cycles, %s edges"
         % (snap["packages"], snap["classes"], snap["cycleCount"], len(snap.get("edges") or [])),
         quiet)
    return snap


def plan(repo: Path, snapshot: Dict[str, Any], limit: int = 6,
         quiet: bool = False) -> List[Dict[str, Any]]:
    """Moves that remove an in-cycle edge and shrink the package graph, best net first."""
    facts = SourceFacts(repo)
    graph = jdeps_runner.class_edges(au.class_dirs(repo))
    if not graph.get("ok"):
        raise RuntimeError("jdeps could not read the classes: %s" % graph.get("why"))

    def accept(cls: str, frm: str, to: str) -> bool:
        # No source here means nothing to move; a destination in another Maven module would
        # put the file where that module's build cannot see it.
        return bool(facts.file_for(cls)) and \
            spoon_plan.package_root(facts, frm) == spoon_plan.package_root(facts, to)

    candidates = plan_moves(snapshot, graph, accept=accept, limit=limit)
    _log("[plan] %d candidates from %d class-level edges"
         % (len(candidates), len(graph["edges"])), quiet)
    return candidates


def _changed_java(original: Path, copy: Path) -> List[Path]:
    """Java files that differ between the original tree and the applied copy."""
    def index(root: Path) -> Dict[str, Path]:
        return {p.relative_to(root).as_posix(): p for p in Path(root).rglob("*.java")
                if "target" not in p.relative_to(root).parts}
    a, b = index(original), index(copy)
    out = [b[k] for k in b if k not in a or b[k].read_bytes() != a[k].read_bytes()]
    out += [a[k] for k in a if k not in b]
    return out


def measure(repo: Path, candidate: Dict[str, Any], snapshot: Dict[str, Any],
            work: Path, baseline_tests: Optional[Dict[str, Any]] = None,
            run_the_tests: bool = True, keep_patch: bool = True,
            quiet: bool = False) -> Dict[str, Any]:
    """Apply one planned move on a copy and return every gate's answer.

    The copy is always discarded; the patch is kept when the change was accepted, because a
    verified refactoring nobody can read is not a deliverable.
    """
    frm, to = candidate["edge"].split(" -> ")
    edit = {"op": "moveClass", "type": candidate["type"], "toPackage": candidate["toPackage"]}
    row: Dict[str, Any] = {"edge": candidate["edge"], "type": candidate["type"],
                           "to_package": candidate["toPackage"],
                           "predicted_removed": candidate["predicted_removed"],
                           "predicted_added": candidate["predicted_added"],
                           "predicted_net": candidate["predicted_net"],
                           "success_criterion": candidate["success_criterion"]}
    t0 = time.time()

    # Free, and before anything is copied: what a move will not fix by itself.
    row["before_apply"] = gates.before_apply(repo, candidate["type"])

    shutil.rmtree(work, ignore_errors=True)
    copy = _copy_repo(repo, work / "copy")
    try:
        facts = SourceFacts(copy)
        root = spoon_plan.source_root_of(facts, candidate["type"])
        rel = str(Path(root).relative_to(copy)) if root else None
        cp = module_classpath(copy, copy / rel) if rel else {"entries": []}
        res = apply_edits(copy, [edit], source_roots=[rel] if rel else None,
                          classpath=cp.get("entries"), log_path=work / "spoon.log")
        row["applied"] = bool(res.get("applied"))
        if not row["applied"]:
            row["why"] = str(((res.get("skipped") or [{}])[0]).get("why", res.get("status")))[:300]
            row["secs"] = round(time.time() - t0)
            return row

        # Seconds, and before the compile: two appliers have left the old name behind.
        row["after_apply"] = gates.after_apply(copy, candidate["type"])
        if not row["after_apply"]["ok"]:
            row.update(verdict=gates.decide(**{k: row[k] for k in
                                               ("before_apply", "after_apply")}),
                       secs=round(time.time() - t0))
            return row

        build = compile_repo(copy, log_path=work / "compile.log", goal="test-compile")
        row["compile"] = build.get("status")
        if not build.get("ok"):
            row["why"] = (build.get("javac_errors") or [""])[0][:300]
            row["verdict"] = {"accepted": False, "failed_gate": "build",
                              "why": row["why"]}
            row["secs"] = round(time.time() - t0)
            return row

        after = au.cycles(copy, log_path=work / "cycles.log")
        row["structural"] = gates.structural(snapshot, after, frm, to)
        jd = jdeps_runner.package_edges(au.class_dirs(copy))
        if jd.get("ok"):
            present = (frm, to) in {tuple(e) for e in jd["edges"]}
            row["jdeps_agrees"] = present is not bool(row["structural"].get("edge_removed"))

        row["changed_files"] = len(_changed_java(repo, copy))
        row["modules"] = modules_for(copy, _changed_java(repo, copy))
        if run_the_tests and row["structural"]["ok"]:
            t = run_tests(copy, log_path=work / "tests.log")
            row["tests"] = {k: t.get(k) for k in ("status", "tests_run", "failures", "errors")}
            row["behavioural"] = gates.behavioural(baseline_tests or {}, t)
        row["verdict"] = gates.decide(**{k: row[k] for k in
                                         ("before_apply", "after_apply", "structural",
                                          "behavioural") if k in row})
        if keep_patch and row["verdict"]["accepted"]:
            row["patch"] = str(write_patch(repo, copy, work.parent / "patches", row))
        row["secs"] = round(time.time() - t0)
        return row
    finally:
        shutil.rmtree(work / "copy", ignore_errors=True)


def write_patch(original: Path, copy: Path, out_dir: Path, row: Dict[str, Any]) -> Path:
    """A unified diff of the Java sources, headed by what was measured.

    The working copy omits .git on purpose -- it is the largest thing in the tree and no
    verification needs it -- so `git diff` inside one compares nothing.
    """
    import difflib

    def index(root: Path) -> Dict[str, Path]:
        return {p.relative_to(root).as_posix(): p for p in Path(root).rglob("*.java")
                if "target" not in p.relative_to(root).parts}

    a, b = index(original), index(copy)
    chunks = []
    for relpath in sorted(set(a) | set(b)):
        old = a[relpath].read_text(encoding="utf-8", errors="ignore").splitlines(True) \
            if relpath in a else []
        new = b[relpath].read_text(encoding="utf-8", errors="ignore").splitlines(True) \
            if relpath in b else []
        if old != new:
            chunks.append("".join(difflib.unified_diff(
                old, new, fromfile="a/" + relpath if old else "/dev/null",
                tofile="b/" + relpath if new else "/dev/null", n=3)))
    tests = row.get("tests") or {}
    header = ("# moveClass %s -> %s\n# %s\n"
              "# measured: %s package edges removed, %s added; %s tests run, "
              "%s failures / %s errors\n"
              % (row["type"], row["to_package"], row["success_criterion"],
                 (row.get("structural") or {}).get("edges_removed"),
                 len((row.get("structural") or {}).get("edges_added") or []),
                 tests.get("tests_run"), tests.get("failures"), tests.get("errors")))
    if (row.get("before_apply") or {}).get("why"):
        header += "# REVIEW: %s\n" % row["before_apply"]["why"]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ("moveClass__%s__to__%s.patch"
                      % (row["type"].rsplit(".", 1)[-1],
                         row["to_package"].rsplit(".", 1)[-1]))
    path.write_text(header + "".join(chunks), encoding="utf-8")
    return path


def run(repo: Path, out_dir: Path, limit: int = 6, run_the_tests: bool = True,
        baseline_tests: Optional[Dict[str, Any]] = None,
        quiet: bool = False) -> List[Dict[str, Any]]:
    """Plan, apply and judge up to `limit` moves. Rows are appended as they are measured."""
    repo, out_dir = Path(repo), Path(out_dir)
    snapshot = baseline(repo, out_dir, quiet=quiet)
    rows_file = out_dir / "rows.jsonl"
    rows = []
    for candidate in plan(repo, snapshot, limit=limit, quiet=quiet):
        row = measure(repo, candidate, snapshot, out_dir / "work",
                      baseline_tests=baseline_tests, run_the_tests=run_the_tests,
                      quiet=quiet)
        rows.append(row)
        with rows_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        v = row.get("verdict") or {}
        _log("  %-26s applied=%-5s accepted=%-5s %s (%ss)"
             % (row["type"].rsplit(".", 1)[-1], row.get("applied"), v.get("accepted"),
                v.get("why") or row.get("why") or "", row.get("secs")), quiet)
    return rows
