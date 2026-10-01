"""Apply a God Component split and measure BOTH metrics, because they disagree.

plan_god_component covers 1,037 of 2,275 observed architecture findings -- Hub-Like, God
Component and Feature Concentration -- by splitting a package: classes sharing a name stem move
into a new sub-package. Two sources say that worsens the dependency graph: 77 of 78 applicable
splits are predicted to add package edges and none to reduce cycle participation, and Arcelli
Fontana's hand-written noModularity tree for Commons Compress measured 108 -> 162 edges with
participation 28 -> 38.

But the split exists to remove a DIFFERENT smell, and a smaller package genuinely stops being a
God Component. So the question is not which prediction is right, it is whether the two metrics
actually point in opposite directions on the same change. That cannot be settled by arithmetic on
one of them.

Each candidate is therefore measured twice over, on the same copy:
    Arcan        total smells and the per-type counts the split is meant to improve
    bytecode     package edges, cycles, and packages sitting in a cycle
plus the gates that decide whether the change is even admissible -- it must build with test
sources, and the project's own suite must be no worse than its recorded baseline.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..refactoring.move_planner import participation
from ..refactoring.strategies import SourceFacts, plan_god_component
from ..tools import archunit_runner as au
from ..tools.arcan_runner import compile_repo, run_tests
from ..tools.spoon_runner import apply_edits, module_classpath
from ..refactoring import spoon_plan
from ..verification import gates
from ..verification.effect_checker import _copy_repo

TARGETS = ("god component", "hub-like dependency", "feature concentration")


def _log(m):
    print(m, flush=True)


def candidates(repo: Path, findings: List[Dict[str, Any]],
               limit: int = 4, max_classes: int = 8) -> List[Dict[str, Any]]:
    """Applicable splits, fewest classes first.

    Fewest first so the first measurement is the smallest possible change: if a two-class split
    already moves both metrics in opposite directions, nothing is gained by starting with twenty.
    """
    facts = SourceFacts(repo)
    out = []
    seen = set()
    for f in findings:
        smell = (f.get("smell_type") or "").lower()
        if smell not in TARGETS:
            continue
        comps = f.get("components") or f.get("affected_components") or []
        plan = plan_god_component(facts, {"components": comps})
        if not getattr(plan, "applicable", True) or not plan.entries:
            continue
        moves = [e.options.get("oldFullyQualifiedTypeName") for e in plan.entries
                 if e.options.get("oldFullyQualifiedTypeName")]
        target = (plan.evidence or {}).get("new_package")
        if not moves or not target or target in seen or len(moves) > max_classes:
            continue
        seen.add(target)
        out.append({"smell": f.get("smell_type"), "package": (plan.evidence or {}).get("package"),
                    "new_package": target, "moves": moves, "reason": plan.reason})
    out.sort(key=lambda c: len(c["moves"]))
    return out[:limit]


def _arcan(repo: Path, out_dir: Path) -> Dict[str, Any]:
    """Arcan's own verdict, which is the metric the split was designed to improve."""
    from ..verification.openrewrite_loop import detect
    d = detect(repo, out_dir, "arcan")
    return {"measured": bool(d.get("measured", d.get("ok"))), "smells": d.get("smells"),
            "by_type": d.get("by_type") or {}}


def measure(repo: Path, candidate: Dict[str, Any], before_bytecode: Dict[str, Any],
            before_arcan: Dict[str, Any], work: Path,
            baseline_tests: Optional[Dict[str, Any]] = None,
            run_the_tests: bool = True) -> Dict[str, Any]:
    """Apply one split on a copy and report both metrics side by side."""
    row = {k: candidate[k] for k in ("smell", "package", "new_package")}
    row["classes_moved"] = len(candidate["moves"])
    t0 = time.time()
    shutil.rmtree(work, ignore_errors=True)
    copy = _copy_repo(repo, work / "copy")
    try:
        facts = SourceFacts(copy)
        edits, roots = [], set()
        for fqn in candidate["moves"]:
            edits.append({"op": "moveClass", "type": fqn,
                          "toPackage": candidate["new_package"]})
            r = spoon_plan.source_root_of(facts, fqn)
            if r:
                roots.add(str(Path(r).relative_to(copy)))
        cp = module_classpath(copy, copy / sorted(roots)[0]) if roots else {"entries": []}
        res = apply_edits(copy, edits, source_roots=sorted(roots) or None,
                          classpath=cp.get("entries"), log_path=work / "spoon.log")
        row["applied"] = bool(res.get("applied"))
        row["applied_count"] = len(res.get("applied") or []) if isinstance(res.get("applied"), list) \
            else (row["classes_moved"] if res.get("applied") else 0)
        if not row["applied"]:
            row.update(why=str(((res.get("skipped") or [{}])[0]).get("why", res.get("status")))[:240],
                       secs=round(time.time() - t0))
            return row

        build = compile_repo(copy, log_path=work / "compile.log", goal="test-compile")
        row["compile"] = build.get("status")
        if not build.get("ok"):
            row.update(why=(build.get("javac_errors") or [""])[0][:240],
                       secs=round(time.time() - t0))
            return row

        after_bytecode = au.cycles(copy, log_path=work / "cycles.log")
        if after_bytecode.get("ok"):
            eb, ea = au.edge_map(before_bytecode), au.edge_map(after_bytecode)
            pb = participation(set(eb)), participation(set(ea))
            row["bytecode"] = {
                "edges_before": len(eb), "edges_after": len(ea),
                "d_edges": len(ea) - len(eb),
                "participation_before": pb[0]["participation"],
                "participation_after": pb[1]["participation"],
                "d_participation": pb[1]["participation"] - pb[0]["participation"],
                "cycles_before": pb[0]["cycles"], "cycles_after": pb[1]["cycles"],
                "largest_before": pb[0]["largest"], "largest_after": pb[1]["largest"],
            }
        after_arcan = _arcan(copy, work / "arcan_after")
        if after_arcan["measured"] and before_arcan.get("measured"):
            keys = set(before_arcan["by_type"]) | set(after_arcan["by_type"])
            row["arcan"] = {
                "smells_before": before_arcan["smells"], "smells_after": after_arcan["smells"],
                "d_smells": (after_arcan["smells"] or 0) - (before_arcan["smells"] or 0),
                "by_type_delta": {k: (after_arcan["by_type"].get(k, 0)
                                      - before_arcan["by_type"].get(k, 0))
                                  for k in sorted(keys)
                                  if after_arcan["by_type"].get(k, 0)
                                  != before_arcan["by_type"].get(k, 0)},
            }
        if run_the_tests:
            t = run_tests(copy, log_path=work / "tests.log")
            row["tests"] = {k: t.get(k) for k in ("status", "tests_run", "failures", "errors")}
            row["behavioural"] = gates.behavioural(baseline_tests or {}, t)
            row["tests_ok"] = row["behavioural"]["ok"]
        row["secs"] = round(time.time() - t0)
        return row
    finally:
        shutil.rmtree(work / "copy", ignore_errors=True)


def run(repo: Path, findings: List[Dict[str, Any]], out_dir: Path, limit: int = 4,
        baseline_tests: Optional[Dict[str, Any]] = None,
        run_the_tests: bool = True) -> List[Dict[str, Any]]:
    repo, out_dir = Path(repo), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    before_bytecode = au.cycles(repo, log_path=out_dir / "before_cycles.log")
    if not before_bytecode.get("ok"):
        raise RuntimeError("oracle blind on the baseline: %s" % before_bytecode.get("why"))
    before_arcan = _arcan(repo, out_dir / "arcan_before")
    base_p = participation(set(au.edge_map(before_bytecode)))
    _log("[baseline] bytecode: %d edges, %d cycles, participation %d | arcan: %s smells"
         % (len(au.edge_map(before_bytecode)), base_p["cycles"], base_p["participation"],
            before_arcan.get("smells")))
    cands = candidates(repo, findings, limit=limit)
    _log("[plan] %d applicable split(s)" % len(cands))
    rows = []
    for c in cands:
        row = measure(repo, c, before_bytecode, before_arcan, out_dir / "work",
                      baseline_tests=baseline_tests, run_the_tests=run_the_tests)
        rows.append(row)
        with (out_dir / "rows.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        b, a = row.get("bytecode") or {}, row.get("arcan") or {}
        _log("  %-28s %d class(es) compile=%-14s | ARCAN %+d smells | BYTECODE %+d edges "
             "%+d participation | tests_ok=%s (%ss)"
             % (row["new_package"].rsplit(".", 1)[-1], row["classes_moved"],
                str(row.get("compile")), a.get("d_smells", 0), b.get("d_edges", 0),
                b.get("d_participation", 0), row.get("tests_ok"), row.get("secs")))
    return rows
