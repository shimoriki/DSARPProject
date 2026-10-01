"""Run the composite extraction across repositories and report what actually happened.

The question this answers is not "is the plan good" but "does the transformation survive contact
with real code". Every earlier source-surgery attempt in this project applied cleanly to a
fixture and failed to compile on a repository, so the outcome recorded here is the compiler's,
never the planner's.

Each candidate passes the same gates as a planned move -- the old name must be gone, the reactor
must build including test sources, the bytecode oracle must agree, the project's own tests must
be no worse -- with one addition: an extraction that compiles but removes no edge is reported as
`applied_no_effect` rather than quietly counted as a win.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..refactoring import extract_to_package
from ..refactoring.move_planner import in_cycle_edges
from ..refactoring.strategies import SourceFacts
from ..tools import archunit_runner as au
from ..tools.arcan_runner import compile_repo, run_tests
from ..verification import gates
from ..verification.effect_checker import _copy_repo
from .edge_measure import baseline


def candidates(repo: Path, snapshot: Dict[str, Any], limit: int = 8,
               min_methods: int = 2) -> List[Dict[str, Any]]:
    """Composite extractions for in-cycle edges, fewest methods first.

    Fewest first because a two-method extraction is a reviewable change and a twenty-method one
    is a redesign; if the operation is going to fail on real code, it should fail cheaply.
    """
    facts = SourceFacts(repo)
    cyclic = in_cycle_edges(snapshot)
    out: List[Dict[str, Any]] = []
    seen = set()
    for edge in snapshot.get("edges") or []:
        if (edge["from"], edge["to"]) not in cyclic:
            continue
        plan = extract_to_package.plan(facts, edge, min_methods=min_methods)
        if not plan or plan["target_class"] in seen:
            continue
        seen.add(plan["target_class"])
        out.append(plan)
    out.sort(key=lambda c: len(c["methods"]))
    return out[:limit]


def measure(repo: Path, candidate: Dict[str, Any], snapshot: Dict[str, Any], work: Path,
            baseline_tests: Optional[Dict[str, Any]] = None,
            run_the_tests: bool = True) -> Dict[str, Any]:
    """Apply one composite extraction on a copy and record every gate's answer."""
    frm, to = candidate["edge"].split(" -> ")
    row = {k: candidate[k] for k in ("edge", "source_class", "target_class", "new_package",
                                     "success_criterion", "sole_carrier")}
    row["methods"] = len(candidate["methods"])
    t0 = time.time()
    shutil.rmtree(work, ignore_errors=True)
    copy = _copy_repo(repo, work / "copy")
    try:
        res = extract_to_package.apply(copy, candidate)
        row["applied"] = bool(res.get("ok"))
        if not row["applied"]:
            row.update(why=res.get("why"), secs=round(time.time() - t0))
            return row
        row["files_touched"] = res.get("files_touched")
        row["methods_moved"] = res.get("methods_moved")

        build = compile_repo(copy, log_path=work / "compile.log", goal="test-compile")
        row["compile"] = build.get("status")
        if not build.get("ok"):
            # The honest headline for this operation: generated Java that does not build.
            row.update(why=(build.get("javac_errors") or [""])[0][:300],
                       verdict={"accepted": False, "failed_gate": "build"},
                       secs=round(time.time() - t0))
            return row

        after = au.cycles(copy, log_path=work / "cycles.log")
        row["structural"] = gates.structural(snapshot, after, frm, to)
        row["edge_removed"] = row["structural"].get("edge_removed")
        row["edges_added"] = len(row["structural"].get("edges_added") or [])
        row["edges_removed"] = row["structural"].get("edges_removed")
        bc, ac = au.cycle_set(snapshot), au.cycle_set(after)
        row["participation_before"] = sum(len(c) for c in bc)
        row["participation_after"] = sum(len(c) for c in ac)
        if not row["edge_removed"]:
            row.update(status="applied_no_effect",
                       verdict={"accepted": False, "failed_gate": "structural",
                                "why": "compiled, but the edge is still there"},
                       secs=round(time.time() - t0))
            return row
        if run_the_tests:
            t = run_tests(copy, log_path=work / "tests.log")
            row["tests"] = {k: t.get(k) for k in ("status", "tests_run", "failures", "errors")}
            row["behavioural"] = gates.behavioural(baseline_tests or {}, t)
        row["verdict"] = gates.decide(**{k: row[k] for k in ("structural", "behavioural")
                                         if k in row})
        row["secs"] = round(time.time() - t0)
        return row
    finally:
        shutil.rmtree(work / "copy", ignore_errors=True)


def run(repo: Path, out_dir: Path, limit: int = 8, run_the_tests: bool = True,
        baseline_tests: Optional[Dict[str, Any]] = None,
        min_methods: int = 2) -> List[Dict[str, Any]]:
    """Plan, apply and judge up to `limit` composite extractions."""
    repo, out_dir = Path(repo), Path(out_dir)
    snapshot = baseline(repo, out_dir)
    cands = candidates(repo, snapshot, limit=limit, min_methods=min_methods)
    print("[extract] %d candidate extraction(s)" % len(cands), flush=True)
    for c in cands:
        print("    %-44s %2d method(s) -> %s"
              % (c["source_class"].rsplit(".", 1)[-1], len(c["methods"]), c["new_package"]),
              flush=True)
    rows_file = out_dir / "extract_rows.jsonl"
    rows = []
    for c in cands:
        row = measure(repo, c, snapshot, out_dir / "extract_work",
                      baseline_tests=baseline_tests, run_the_tests=run_the_tests)
        rows.append(row)
        with rows_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        v = row.get("verdict") or {}
        print("  %-28s applied=%-5s compile=%-14s edge_removed=%-5s accepted=%-5s %s (%ss)"
              % (row["source_class"].rsplit(".", 1)[-1], row.get("applied"),
                 str(row.get("compile")), row.get("edge_removed"), v.get("accepted"),
                 (v.get("why") or row.get("why") or "")[:60], row.get("secs")), flush=True)
    return rows
