"""Freeze LLM plans on the beam arm's own targets.

    py -m dsarp.agentic.run REPO OUT --targets-from PRE --model NAME [--base-url URL]
                            [--api-key-env VAR] --freeze

Targets come from a beam preregistration, so both arms work on identical cycles. Each LLM plan is
dry-run by Spoon; a class Spoon refuses is banned and the planner is asked again, as `make_plans`
does for the beam arm. A model failure stays in that target's plan dict and the run continues.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

from ..experiments.mixed_plan import dry_run
from ..experiments.scc_dissolve import (PLAN_ATTEMPTS, arm_matches, cannot_freeze, facade_first, freeze,
                                        plan_targets,
                                        measure, move_accept, prepare, summarise)
from ..models.providers import DEFAULT_BASE_URL, LocalProvider
from ..refactoring.inversion_facts import InversionFacts
from ..refactoring.scc_planner import top_level_edges
from ..refactoring.strategies import SourceFacts
from ..tools import arcan_runner
from ..tools.arcan_runner import compile_repo, run_tests
from ..verification import gates
from .planner import llm_plan
from .repair import repair


def targets_from(path: Path) -> List[List[str]]:
    return [p["component"] for p in json.loads(Path(path).read_text(encoding="utf-8"))["plans"]]


def _accept_for(repo: Path, banned: set) -> Callable[[str, str], bool]:
    return move_accept(SourceFacts(repo), banned)


def make_llm_plans(repo: Path, base: Dict[str, Any], model, targets: List[List[str]], work: Path,
                   rounds: int = 3) -> List[Dict[str, Any]]:
    edges = top_level_edges(tuple(e) for e in base["edges"])
    inv_facts = InversionFacts(base.get("snapshot") or {}, SourceFacts(repo))
    plans = []
    for comp in targets:
        banned: set = set()
        found: Dict[str, Any] = {}

        def blocked(consumer: str, impl: str, moved: Dict[str, str]):
            # Spoon names a refused inversion by the impl's name after the plan's moves.
            new = "%s.%s" % (moved[impl], impl.rsplit(".", 1)[1]) if impl in moved else impl
            return "refused by Spoon" if impl in banned or new in banned else \
                inv_facts.blocked(consumer, impl, moved)
        for _ in range(PLAN_ATTEMPTS):
            found = llm_plan(model, edges, set(comp), _accept_for(repo, banned), blocked, rounds=rounds)
            if not found["moves"] and not found["inversions"]:
                break
            verdict = dry_run(repo, found, work)
            if verdict.get("ok") or not verdict.get("refused"):
                found["dry_run"] = verdict
                break
            banned.add(verdict["refused"])
        shutil.rmtree(work, ignore_errors=True)
        plans.append({**found, "refused": sorted(banned)})
        print("%s: %d moves, %d inversions, predicted left %s%s" % (
            comp, len(found.get("moves") or []), len(found.get("inversions") or []),
            found.get("predicted_left"), " (%s)" % found["why"] if found.get("why") else ""), flush=True)
    return plans


def check_frozen(out: Path, arm: Dict[str, Any]) -> Dict[str, Any]:
    pre = json.loads((out / "preregistration.json").read_text(encoding="utf-8"))
    if not arm_matches(pre.get("arm", arm), arm):
        raise SystemExit("frozen for %s, not %s" % (pre.get("arm"), arm))
    return pre


def make_hook(model, budget: int, baseline_tests: Dict[str, Any]) -> Callable:
    """measure's repair hook: (copy, stage, failure, scope). Build stage rebuilds by test-compile;
    test stage rebuilds and reruns the suite, ok when nothing fails that passed at baseline."""
    def hook(copy: Path, stage: str, failure: str, scope) -> Dict[str, Any]:
        log = copy.parent / ("repair_%s.log" % stage)

        def rebuild() -> Dict[str, Any]:
            b = compile_repo(copy, log_path=log, goal="test-compile")
            text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
            if not b.get("ok") or stage == "build":
                return {"ok": bool(b.get("ok")), "log": text}
            t = run_tests(copy, timeout=4 * 3600, log_path=copy.parent / "repair_tests.log")
            beh = gates.behavioural(baseline_tests, t)
            return {"ok": not beh.get("newly_failing"), "log": "\n".join(beh.get("newly_failing") or [])}
        return {"stage": stage, "scope": sorted(scope), **repair(model, copy, set(scope), failure, rebuild, budget)}
    return hook


def arm_for(model: str, engine: str, facades: bool) -> Dict[str, Any]:
    return {"engine": engine, "facades": facades, "operators": "mixed", "repair": False,
            "planner": "llm", "model": model}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--targets-from", type=Path, required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--api-key-env", default="DSARP_LLM_KEY")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--engine", choices=("spoon", "text", "rewrite"), default="text")
    ap.add_argument("--facades", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--repair-budget", type=int, default=0)
    # Hosted models, as in hpc/smoke.py: seconds between calls, longest 429 wait to sit out,
    # per-call timeout, and no output cap so a reasoning model can finish its answer.
    ap.add_argument("--min-interval", type=float, default=0)
    ap.add_argument("--max-wait", type=float, default=300)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--uncapped", action="store_true")
    # Plan for Arcan's package cycle clusters (beam defaults: size <= 15, first 10) instead of
    # the targets file; the file still locates baseline_tests.json.
    ap.add_argument("--arcan-targets", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    model = LocalProvider(a.model, a.base_url, timeout=a.timeout, uncapped=a.uncapped,
                          api_key=os.environ.get(a.api_key_env) or "dsarp-local",
                          min_interval=a.min_interval, max_wait=a.max_wait)
    print("java level %s, JDK %s" % arcan_runner.select_jdk(a.repo), flush=True)
    base = prepare(a.repo, a.out)
    targets = ([sorted(c) for c in plan_targets(base["edges"], 15, 10, a.out / "arcan_before" / "arcan")]
               if a.arcan_targets else targets_from(a.targets_from))
    tests_file = a.targets_from.parent / "baseline_tests.json"
    tests = json.loads(tests_file.read_text(encoding="utf-8")) if tests_file.exists() else None
    arm = arm_for(a.model, a.engine, a.facades)
    if a.arcan_targets:
        arm["targets"] = "arcan"   # absent on older freezes, which took the beam's jdeps targets
    if a.confirm:
        pre = check_frozen(a.out, arm)
        hook = make_hook(model, a.repair_budget, tests) if a.repair_budget else None
        rows = []
        name = "rows_repair.jsonl" if a.repair_budget else "rows.jsonl"
        with (a.out / name).open("a", encoding="utf-8") as f:
            for p in pre["plans"]:
                t0 = time.time()
                once = lambda p_, fac: {**measure(a.repo, p_, base, a.out, tests, a.engine, fac, hook),
                                        "repair_budget": a.repair_budget}
                r = {**(facade_first(once, p) if a.facades else once(p, False)), "secs": round(time.time() - t0)}
                rows.append(r)
                f.write(json.dumps(r, default=str) + "\n")
                f.flush()
                print("%s: stage=%s level=%s left=%s" % (p["component"], r.get("stage"), r.get("level"),
                                                         r.get("measured_left")), flush=True)
        summary = summarise(rows)
        (a.out / name.replace("rows", "summary").replace(".jsonl", ".json")).write_text(
            json.dumps(summary, indent=1), encoding="utf-8")
        print(json.dumps(summary, indent=1), flush=True)
        return
    if a.freeze:
        why = cannot_freeze(tests)
        if why:
            raise SystemExit("not frozen: " + why)
        plans = make_llm_plans(a.repo, base, model, targets, a.out / "work", a.rounds)
        print("frozen:", freeze(a.repo, a.out, plans, max(len(t) for t in targets), len(targets), arm),
              flush=True)


if __name__ == "__main__":
    main()
