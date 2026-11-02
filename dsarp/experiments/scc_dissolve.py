"""The cycle-repair loop: plan a set of moves for each small SCC, apply it, and judge it.

The order is the order of cost, as in edge_measure. Selection is frozen before anything is
applied when `--freeze` is used: `preregistration.json` holds targets, plans and tool hashes,
and `--confirm` runs exactly those. Confirmatory runs never re-plan.

    py -m dsarp.experiments.scc_dissolve <repo> <out> --max-size 15 --limit 10 [--no-tests]
    py -m dsarp.experiments.scc_dissolve <repo> <out> --freeze
    py -m dsarp.experiments.scc_dissolve <repo> <out> --confirm
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .arcan_diff import cycle_sets
from .edge_measure import _changed_java, write_patch
from ..refactoring import scc_planner, spoon_plan
from ..refactoring.name_refs import service_providers
from ..refactoring.strategies import SourceFacts
from ..tools import api_runner, archunit_runner as au, jdeps_runner
from ..tools.arcan_runner import arcan_jar, compile_repo, detect_with_arcan, run_tests
from ..tools.spoon_runner import apply_edits, module_classpath
from ..verification import gates
from ..verification.effect_checker import _copy_repo


def _sha(path: Optional[Path]) -> Optional[str]:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else None


def prepare(repo: Path, out: Path) -> Dict[str, Any]:
    """Baseline snapshot, class graph and Arcan run, cached: unmodified source cannot change."""
    cache = out / "baseline.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    built = compile_repo(repo, log_path=out / "baseline_compile.log", goal="test-compile")
    if not built.get("ok"):
        raise RuntimeError("baseline does not compile: %s" % (built.get("javac_errors") or built["status"]))
    snap = au.cycles(repo, log_path=out / "baseline_cycles.log")
    if not snap.get("ok"):
        raise RuntimeError("oracle blind on the baseline: %s" % snap.get("why"))
    graph = jdeps_runner.class_edges(au.class_dirs(repo))
    if not graph.get("ok"):
        raise RuntimeError("jdeps could not read the classes: %s" % graph.get("why"))
    arcan = detect_with_arcan(repo, out / "arcan_before")
    data = {"snapshot": snap, "edges": graph["edges"], "arcan": arcan.get("by_type"),
            "services": service_providers(repo)}
    cache.write_text(json.dumps(data), encoding="utf-8")
    return data


def make_plans(repo: Path, base: Dict[str, Any], max_size: int, limit: int) -> List[Dict[str, Any]]:
    facts = SourceFacts(repo)
    edges = scc_planner.top_level_edges(tuple(e) for e in base["edges"])
    comps = [c for c in scc_planner.components(scc_planner.package_edges(edges, {}))
             if len(c) <= max_size][:limit]

    def accept(cls: str, dest: str) -> bool:
        # No source here means nothing to move; another module's build cannot see the file.
        return bool(facts.file_for(cls)) and \
            spoon_plan.package_root(facts, cls.rsplit(".", 1)[0]) == spoon_plan.package_root(facts, dest)

    return [scc_planner.plan(edges, c, accept) for c in comps]


def _apply(copy: Path, moves: List[List[str]], work: Path) -> Dict[str, Any]:
    facts = SourceFacts(copy)
    by_root: Dict[str, List[Dict[str, str]]] = {}
    for cls, dest in moves:
        root = spoon_plan.source_root_of(facts, cls)
        if not root:
            return {"applied": False, "why": "no source root for %s" % cls}
        by_root.setdefault(str(Path(root).relative_to(copy)), []).append(
            {"op": "moveClass", "type": cls, "toPackage": dest})
    for rel, edits in by_root.items():
        cp = module_classpath(copy, copy / rel)
        res = apply_edits(copy, edits, source_roots=[rel], classpath=cp.get("entries"),
                          log_path=work / "spoon.log")
        if len(res.get("applied") or []) != len(edits):
            return {"applied": False,
                    "why": str((res.get("skipped") or [{}])[0].get("why", res.get("status")))[:300]}
    return {"applied": True}


def _arcan_target_gone(comp: List[str], before: Path, after: Path) -> bool:
    members = set(comp)
    return not any(members <= c for c in cycle_sets(after, "package")) and \
        any(members <= c for c in cycle_sets(before, "package"))


def _regressions(row: Dict[str, Any], plan_: Dict[str, Any]) -> List[str]:
    if row.get("level") == "4c":
        return [au.regression_rule(a, b) for a in plan_["component"] for b in plan_["component"]
                if a != b and row.get("edge_gone", {}).get("%s -> %s" % (a, b))]
    return []


def measure(repo: Path, plan_: Dict[str, Any], base: Dict[str, Any], out: Path,
            baseline_tests: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    t0 = time.time()
    comp, moves = set(plan_["component"]), plan_["moves"]
    row: Dict[str, Any] = {"component": plan_["component"], "size": plan_["size"], "moves": moves,
                           "predicted_left": plan_["predicted_left"],
                           "success_criterion": "%d of %d packages stay in a cycle"
                                                % (plan_["predicted_left"], plan_["size"])}
    if not moves:
        return {**row, "stage": "no_plan", "level": "0"}
    work = out / "work"
    shutil.rmtree(work, ignore_errors=True)
    copy = _copy_repo(repo, work / "copy")
    try:
        row["before_apply"] = [gates.before_apply(repo, c) for c, _ in moves]
        applied = _apply(copy, moves, work)
        if not applied["applied"]:
            return {**row, **applied, "stage": "apply", "level": "1",
                    "verdict": {"accepted": False, "state": "FAIL", "failed_gate": "apply"}}
        residue = [gates.after_apply(copy, c) for c, _ in moves]
        bad = next((r for r in residue if not r["ok"]), {"ok": True})
        changed = _changed_java(repo, copy)
        row["changed_files"] = len(changed)
        build = compile_repo(copy, log_path=work / "compile.log", goal="test-compile")
        row["compile"] = build.get("status")
        if not build.get("ok"):
            return {**row, "stage": "build", "level": "1",
                    "why": (build.get("javac_errors") or [""])[0][:300],
                    "verdict": {"accepted": False, "state": "FAIL", "failed_gate": "build"}}
        snap = base["snapshot"]
        after = au.cycles(copy, log_path=work / "cycles.log")
        comparable = gates.comparable(snap, after)
        before_sets, after_sets = au.cycle_set(snap), au.cycle_set(after)
        still = [c for c in after_sets if c & comp]
        gone = {"%s -> %s" % (a, b): au.edge_verdict(snap, after, a, b).get("edge_removed")
                for a in comp for b in comp
                if a != b and (a, b) in {tuple(k) for k in au.edge_map(snap)}}
        row.update(measured_left=sum(len(c & comp) for c in still), edge_gone=gone,
                   novel_cycles=[sorted(c) for c in au.novel_cycles(before_sets, after_sets)])
        renames = {c: "%s.%s" % (d, c.rsplit(".", 1)[1]) for c, d in moves}
        dispatch = gates.dispatch(base.get("services") or {}, service_providers(copy), renames)
        structural = {"ok": bool(comparable["ok"] and not row["novel_cycles"]
                                 and row["measured_left"] < plan_["size"]),
                      "why": comparable.get("why") or ("nothing left the cycle"
                                                       if row["measured_left"] >= plan_["size"]
                                                       else "a new cycle appeared")}
        arcan = detect_with_arcan(copy, work / "arcan_after")
        target_gone = _arcan_target_gone(plan_["component"], out / "arcan_before" / "arcan",
                                         work / "arcan_after" / "arcan")
        row.update(arcan_after=arcan.get("by_type"), arcan_target_gone=target_gone)
        modules = sorted({p.relative_to(copy if copy in p.parents else repo).parts[0]
                          for p in changed})
        row["api"] = api_runner.report(repo, copy, modules)
        behavioural = None
        if structural["ok"] and bad["ok"] and dispatch["ok"] and baseline_tests is not None:
            t = run_tests(copy, timeout=4 * 3600, log_path=work / "tests.log")
            row["tests"] = {k: t.get(k) for k in ("status", "tests_run", "failures", "errors",
                                                  "partial", "skipped_modules")}
            behavioural = gates.behavioural(baseline_tests, t)
        row["verdict"] = gates.decide(after_apply=bad, structural=structural, dispatch=dispatch,
                                      behavioural=behavioural or
                                      {"ok": False, "state": "INVALID", "why": "tests were not run"},
                                      api=row["api"])
        state = (behavioural or {}).get("state", "INVALID")
        row["level"] = scc_planner.level(comp, list(before_sets), list(after_sets),
                                         sum(1 for v in gone.values() if v), state, target_gone)
        row["regression_rules"] = _regressions(row, plan_)
        if row["verdict"]["accepted"]:
            row["patch"] = str(write_patch(repo, copy, out / "patches", {
                **row, "type": moves[0][0], "to_package": moves[0][1]}))
        return {**row, "stage": "judged"}
    finally:
        row["secs"] = round(time.time() - t0)
        shutil.rmtree(work / "copy", ignore_errors=True)


def freeze(repo: Path, out: Path, plans: List[Dict[str, Any]], max_size: int, limit: int) -> Path:
    path = out / "preregistration.json"
    if path.exists():
        raise SystemExit("already frozen: %s" % path)
    path.write_text(json.dumps({
        "selection": {"max_size": max_size, "limit": limit, "order": "SCC size ascending"},
        "invalid_rule": "INVALID counts as not-success and is reported on its own row",
        "graph": "jdeps class edges, one directory at a time, nested classes folded",
        "arcan_sha256": _sha(arcan_jar()), "oracle_sha256": _sha(au.JAR) if Path(au.JAR).exists() else None,
        "plans": plans}, indent=1), encoding="utf-8")
    return path


def summarise(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """A funnel, by level and state. INVALID stays in the denominator as not-success."""
    levels: Dict[str, int] = {}
    states: Dict[str, int] = {}
    for r in rows:
        levels[r.get("level", "?")] = levels.get(r.get("level", "?"), 0) + 1
        s = (r.get("verdict") or {}).get("state", "n/a")
        states[s] = states.get(s, 0) + 1
    success = [r for r in rows if r.get("level") in ("4a", "4b", "4c", "5")]
    no_break = [r for r in success if (r.get("api") or {}).get("ok")]
    return {"targets": len(rows), "levels": levels, "states": states,
            "dissolved": levels.get("4c", 0), "success": len(success),
            "success_without_api_break": len(no_break)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repo", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--max-size", type=int, default=15)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--no-tests", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    # Measure the baseline on a fresh copy, built exactly as candidates are. A comment-only
    # placebo moved log4j2's largest cycle 50 -> 49 when compared with the repository's own
    # build, so a delta between differently built trees is not a delta.
    a.repo = a.repo.resolve()
    tree = a.out / "baseline_tree"
    if not tree.exists():
        _copy_repo(a.repo, tree)
    a.repo = tree
    base = prepare(a.repo, a.out)
    if a.confirm:
        plans = json.loads((a.out / "preregistration.json").read_text(encoding="utf-8"))["plans"]
    else:
        plans = make_plans(a.repo, base, a.max_size, a.limit)
    if a.freeze:
        print("frozen:", freeze(a.repo, a.out, plans, a.max_size, a.limit))
        return
    tests = None
    if not a.no_tests:
        cache = a.out / "baseline_tests.json"
        if cache.exists():
            tests = json.loads(cache.read_text(encoding="utf-8"))
        else:
            tests = run_tests(a.repo, timeout=4 * 3600, log_path=a.out / "baseline_tests.log")
            cache.write_text(json.dumps(tests), encoding="utf-8")
        print("baseline tests:", {k: tests.get(k) for k in
                                  ("tests_run", "failures", "errors", "partial", "skipped_modules")}, flush=True)
    rows = []
    with (a.out / "rows.jsonl").open("a", encoding="utf-8") as f:
        for p in plans:
            print("target size %d: %d moves, predicted left %d" % (p["size"], len(p["moves"]), p["predicted_left"]), flush=True)
            r = measure(a.repo, p, base, a.out, tests)
            rows.append(r)
            f.write(json.dumps(r, default=str) + "\n")
            f.flush()
            print("  stage=%s level=%s left=%s %s" % (r.get("stage"), r.get("level"), r.get("measured_left"),
                                                      (r.get("verdict") or {}).get("why") or r.get("why") or ""), flush=True)
    summary = summarise(rows)
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
