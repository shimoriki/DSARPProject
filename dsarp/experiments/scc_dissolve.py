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
from ..refactoring.name_refs import rewrite_names, service_providers
from ..refactoring.strategies import SourceFacts
from ..tools import api_runner, archunit_runner as au, jdeps_runner
from ..tools.arcan_runner import arcan_jar, compile_repo, detect_with_arcan, run_tests
from ..openrewrite.runner import run_recipe, write_move_recipe
from ..refactoring.facades import add_facades
from ..refactoring.text_move import move_classes
from ..tools.spoon_runner import apply_edits, module_classpath
from ..verification import gates
from ..verification.effect_checker import _copy_repo


RERUNS = 3
PLAN_ATTEMPTS = 5


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


def make_plans(repo: Path, base: Dict[str, Any], max_size: int, limit: int,
               work: Path) -> List[Dict[str, Any]]:
    facts = SourceFacts(repo)
    edges = scc_planner.top_level_edges(tuple(e) for e in base["edges"])
    comps = [c for c in scc_planner.components(scc_planner.package_edges(edges, {}))
             if len(c) <= max_size][:limit]

    def legal(comp: set) -> Dict[str, Any]:
        """Plan, dry-run on a copy, ban what Spoon refuses and plan again.

        pdfbox lost 2 of 4 targets to moves Spoon refused for visibility, which the class graph
        cannot see. Asking Spoon is the authority, and doing it here keeps a frozen plan final.
        """
        banned: set = set()

        def accept(cls: str, dest: str) -> bool:
            # No source here means nothing to move; another module's build cannot see the file.
            return cls not in banned and bool(facts.file_for(cls)) and \
                spoon_plan.source_root_of(facts, cls) == spoon_plan.package_root(facts, dest)

        for _ in range(PLAN_ATTEMPTS):
            found = scc_planner.plan(edges, comp, accept)
            if not found["moves"]:
                break
            shutil.rmtree(work, ignore_errors=True)
            # Spoon on purpose, whatever writes the result: its refusal is the legality check.
            done = _apply(_copy_repo(repo, work / "copy"), found["moves"], work, "spoon")
            if done["applied"] or not done.get("refused"):
                break
            banned.add(done["refused"])
        shutil.rmtree(work, ignore_errors=True)
        return {**found, "refused": sorted(banned)}

    return [legal(c) for c in comps]


def _apply_rewrite(copy: Path, moves: List[List[str]], work: Path) -> Dict[str, Any]:
    recipe = write_move_recipe(copy, [(c, "%s.%s" % (d, c.rsplit(".", 1)[1])) for c, d in moves],
                               include_text=False)      # rewrite_names does the text files
    res = run_recipe(copy, log_path=work / "rewrite.log")
    recipe.unlink(missing_ok=True)
    if res.get("status") != "changed":
        return {"applied": False, "why": "%s: %s" % (res.get("status"), (res.get("errors") or [""])[0][:250])}
    return {"applied": True}


def _apply(copy: Path, moves: List[List[str]], work: Path, engine: str = "spoon") -> Dict[str, Any]:
    if engine == "rewrite":
        return _apply_rewrite(copy, moves, work)
    facts = SourceFacts(copy)
    if engine == "text":
        roots = [(spoon_plan.source_root_of(facts, c), c, d) for c, d in moves]
        missing = [c for r, c, _ in roots if not r]
        return {"applied": False, "why": "no source root for %s" % missing[0]} if missing \
            else move_classes(copy, roots)
    by_root: Dict[str, List[Dict[str, str]]] = {}
    for cls, dest in moves:
        root = spoon_plan.source_root_of(facts, cls)
        if not root:
            return {"applied": False, "why": "no source root for %s" % cls}
        by_root.setdefault(str(Path(root).relative_to(copy)), []).append(
            {"op": "moveClass", "type": cls, "toPackage": dest, "group": dest})
    for rel, edits in by_root.items():
        cp = module_classpath(copy, copy / rel)
        res = apply_edits(copy, edits, source_roots=[rel], classpath=cp.get("entries"),
                          log_path=work / "spoon.log")
        if len(res.get("applied") or []) != len(edits):
            first = (res.get("skipped") or [{}])[0]
            return {"applied": False, "refused": (first.get("edit") or {}).get("type"),
                    "why": str(first.get("why", res.get("status")))[:300]}
    return {"applied": True}


def _modules(changed: List[Path], repo: Path, copy: Path) -> List[str]:
    """The build modules touched: the nearest directory with classes, nested or at the root."""
    out = set()
    for p in changed:
        root = copy if copy in p.parents else repo
        home = next((q for q in p.parents if (q / "target/classes").is_dir()), None)
        if home and (home == root or root in home.parents):
            out.add(home.relative_to(root).as_posix())
    return sorted(out)


def _arcan_target_gone(comp: List[str], before: Path, after: Path) -> bool:
    members = set(comp)
    return not any(members <= c for c in cycle_sets(after, "package")) and \
        any(members <= c for c in cycle_sets(before, "package"))


def _regressions(row: Dict[str, Any], plan_: Dict[str, Any]) -> List[str]:
    if row.get("level") == "4c":
        return [au.regression_rule(a, b) for a in plan_["component"] for b in plan_["component"]
                if a != b and row.get("edge_gone", {}).get("%s -> %s" % (a, b))]
    return []


def _rerun(repo: Path, copy: Path, suspects: List[str], work: Path, times: int = RERUNS):
    """Outcomes of the suspects' test classes, `times` runs on each tree."""
    classes = sorted({t.split("#")[0].split("$")[0] for t in suspects})

    def runs(tree: Path, name: str) -> List[Dict[str, str]]:
        return [run_tests(tree, timeout=3600, log_path=work / ("%s%d.log" % (name, i)),
                          only=classes).get("outcomes") or {} for i in range(times)]

    return runs(repo, "rerun_base"), runs(copy, "rerun_cand")


def _patch_row(row: Dict[str, Any], moves: List[List[str]]) -> Dict[str, Any]:
    """write_patch describes one move; a plan has several, each with its own before_apply."""
    risk = next((b for b in row.get("before_apply") or [] if b.get("why")), None)
    return {**row, "before_apply": risk, "type": ", ".join(c for c, _ in moves),
            "to_package": ", ".join(d for _, d in moves)}


def measure(repo: Path, plan_: Dict[str, Any], base: Dict[str, Any], out: Path,
            baseline_tests: Optional[Dict[str, Any]], engine: str = "text",
            facades: bool = False) -> Dict[str, Any]:
    comp, moves = set(plan_["component"]), plan_["moves"]
    row: Dict[str, Any] = {"engine": engine, "component": plan_["component"],
                           "size": plan_["size"], "moves": moves,
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
        applied = _apply(copy, moves, work, engine)
        if not applied["applied"]:
            return {**row, **applied, "stage": "apply", "level": "1",
                    "verdict": {"accepted": False, "state": "FAIL", "failed_gate": "apply"}}
        row["rewritten"] = rewrite_names(copy, {c: "%s.%s" % (d, c.rsplit(".", 1)[1]) for c, d in moves})
        residue = [gates.after_apply(copy, c) for c, _ in moves]
        bad = next((r for r in residue if not r["ok"]), {"ok": True})
        if facades:
            # After the old-name check, which a facade would fail by design.
            row["facades"] = add_facades(repo, copy, moves)
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
        row["api"] = api_runner.report(repo, copy, _modules(changed, repo, copy))
        behavioural = None
        if structural["ok"] and bad["ok"] and dispatch["ok"] and baseline_tests is not None:
            t = run_tests(copy, timeout=4 * 3600, log_path=work / "tests.log")
            row["tests"] = {k: t.get(k) for k in ("status", "tests_run", "failures", "errors",
                                                  "partial", "skipped_modules")}
            behavioural = gates.behavioural(baseline_tests, t)
            suspects = behavioural.get("newly_failing") or []
            if suspects and behavioural.get("extra_failures", 0) <= len(suspects):
                behavioural = gates.settle_flakes(behavioural, *_rerun(repo, copy, suspects, work))
            row["behavioural"] = {k: behavioural.get(k) for k in ("state", "newly_failing", "flaky",
                                                                  "appeared")}
        row["reflection"] = gates.reflection(repo, copy)
        row["verdict"] = gates.decide(after_apply=bad, reflection=row["reflection"],
                                      structural=structural, dispatch=dispatch,
                                      behavioural=behavioural or
                                      {"ok": False, "state": "INVALID", "why": "tests were not run"},
                                      api=row["api"])
        state = (behavioural or {}).get("state", "INVALID")
        row["level"] = scc_planner.level(comp, list(before_sets), list(after_sets),
                                         sum(1 for v in gone.values() if v), state, target_gone)
        row["regression_rules"] = _regressions(row, plan_)
        if row["verdict"]["accepted"]:
            row["patch"] = str(write_patch(repo, copy, out / "patches", _patch_row(row, moves)))
        return {**row, "stage": "judged"}
    finally:
        shutil.rmtree(work / "copy", ignore_errors=True)


def facade_first(measure_once, plan_: Dict[str, Any]) -> Dict[str, Any]:
    """Measure with facades, and again without when they broke the build or the cycle.

    A facade adds an edge from the old package to the new one; on pdfbox it closed the cycle
    again. Both refusals come before the tests, so the second attempt costs one build.
    """
    first = measure_once(plan_, True)
    gate = (first.get("verdict") or {}).get("failed_gate")
    if not first.get("facades") or gate not in ("build", "structural"):
        return first
    return {**measure_once(plan_, False),
            "facade_fallback": {"failed_gate": gate, "level": first.get("level"),
                                "measured_left": first.get("measured_left"),
                                "why": (first.get("verdict") or {}).get("why") or first.get("why"),
                                "facades": first["facades"]}}


def cannot_freeze(tests: Any) -> Any:
    """Why these baseline tests cannot support a confirmatory run: a partial one accepts nothing.

    struts and karaf froze nine targets on partial baselines, and none could have passed.
    """
    if not tests:
        return "the baseline tests were not run"
    if tests.get("partial"):
        return "the baseline skipped %s" % tests.get("skipped_modules")
    return None


def freeze(repo: Path, out: Path, plans: List[Dict[str, Any]], max_size: int, limit: int,
           arm: Dict[str, Any]) -> Path:
    path = out / "preregistration.json"
    if path.exists():
        raise SystemExit("already frozen: %s" % path)
    path.write_text(json.dumps({
        "selection": {"max_size": max_size, "limit": limit, "order": "SCC size ascending"},
        "arm": arm,
        "invalid_rule": "INVALID counts as not-success and is reported on its own row",
        "flake_rule": "a newly failing test's class reruns %d times on each tree; regression "
                      "when the candidate fails more reruns than the baseline" % RERUNS,
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
    # Text by default: on 8 frozen targets it was accepted 7 times to Spoon's 6 and OpenRewrite's
    # 6, and alone rewrote nothing beyond the move.
    ap.add_argument("--engine", choices=("spoon", "text", "rewrite"), default="text",
                    help="what writes the moves; plans are still checked for legality by Spoon")
    ap.add_argument("--facades", action="store_true",
                    help="leave a deprecated delegating type at each moved public class's old name; "
                         "measured again without them when they break the build or the cycle")
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
    if a.freeze:
        why = cannot_freeze(tests)
        if why:
            raise SystemExit("not frozen: " + why)
    # Operators and repair are fixed until the mixed and repair arms land; they are recorded now
    # so a later freeze cannot be confirmed by a run with other operators.
    arm = {"engine": a.engine, "facades": a.facades, "operators": "moves", "repair": False}
    if a.confirm:
        pre = json.loads((a.out / "preregistration.json").read_text(encoding="utf-8"))
        # Older freezes named no arm, or only engine and facades: they were all moves, unrepaired.
        if {"operators": "moves", "repair": False, **pre.get("arm", arm)} != arm:
            raise SystemExit("frozen for %s, not %s" % (pre["arm"], arm))
        plans = pre["plans"]
    else:
        plans = make_plans(a.repo, base, a.max_size, a.limit, a.out / "work")
    if a.freeze:
        print("frozen:", freeze(a.repo, a.out, plans, a.max_size, a.limit, arm))
        return
    rows = []
    with (a.out / "rows.jsonl").open("a", encoding="utf-8") as f:
        for p in plans:
            print("target size %d: %d moves, predicted left %d" % (p["size"], len(p["moves"]), p["predicted_left"]), flush=True)
            t0 = time.time()
            once = lambda p_, fac: measure(a.repo, p_, base, a.out, tests, a.engine, fac)
            r = {**(facade_first(once, p) if a.facades else once(p, False)),
                 "secs": round(time.time() - t0)}
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
