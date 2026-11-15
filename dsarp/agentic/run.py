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
from pathlib import Path
from typing import Any, Callable, Dict, List

from ..experiments.mixed_plan import dry_run
from ..experiments.scc_dissolve import (PLAN_ATTEMPTS, cannot_freeze, freeze, move_accept, prepare)
from ..models.providers import DEFAULT_BASE_URL, LocalProvider
from ..refactoring.inversion_facts import InversionFacts
from ..refactoring.scc_planner import top_level_edges
from ..refactoring.strategies import SourceFacts
from ..tools import arcan_runner
from .planner import llm_plan


def targets_from(path: Path) -> List[List[str]]:
    return [p["component"] for p in json.loads(Path(path).read_text(encoding="utf-8"))["plans"]]


def _accept_for(repo: Path, banned: set) -> Callable[[str, str], bool]:
    return move_accept(SourceFacts(repo), banned)


def make_llm_plans(repo: Path, base: Dict[str, Any], model, targets: List[List[str]], work: Path,
                   rounds: int = 3) -> List[Dict[str, Any]]:
    edges = top_level_edges(tuple(e) for e in base["edges"])
    blocked = InversionFacts(base.get("snapshot") or {}, SourceFacts(repo)).blocked
    plans = []
    for comp in targets:
        banned: set = set()
        found: Dict[str, Any] = {}
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
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    model = LocalProvider(a.model, a.base_url, api_key=os.environ.get(a.api_key_env) or "dsarp-local")
    print("java level %s, JDK %s" % arcan_runner.select_jdk(a.repo), flush=True)
    base = prepare(a.repo, a.out)
    targets = targets_from(a.targets_from)
    if a.freeze:
        tests_file = a.targets_from.parent / "baseline_tests.json"
        tests = json.loads(tests_file.read_text(encoding="utf-8")) if tests_file.exists() else None
        why = cannot_freeze(tests)
        if why:
            raise SystemExit("not frozen: " + why)
        plans = make_llm_plans(a.repo, base, model, targets, a.out / "work", a.rounds)
        print("frozen:", freeze(a.repo, a.out, plans, max(len(t) for t in targets), len(targets),
                                arm_for(a.model, a.engine, a.facades)), flush=True)


if __name__ == "__main__":
    main()
