"""Ask an LLM for OpenRewrite recipes on the smells DSARP has no strategy for, then test them.

Two stages, and the second one is the point:

  PROPOSE   the model sees the smell, the component, and hard facts from the source index,
            and must answer with recipes drawn only from a fixed catalogue
  TEST      each validated proposal runs through the real closed loop; it is viable only if
            the code still compiles AND the targeted smell measurably drops

Validation alone (before anything runs) already catches the dominant failure mode: invented
recipe names, options that do not exist, and types that are not in the repository.

    py scripts/run_ai_recipes.py --repo apache-commons-validator
    py scripts/run_ai_recipes.py --repo apache-commons-validator --execute   # also run them
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dsarp.config import load_config                                     # noqa: E402
from dsarp.models.providers import get_provider                          # noqa: E402
from dsarp.refactoring.agents import plan_all                            # noqa: E402
from dsarp.refactoring.ai_recipes import propose, test_proposal          # noqa: E402
from dsarp.refactoring.strategies import SourceFacts                     # noqa: E402
from dsarp.repositories.manager import RepositoryManager                 # noqa: E402
from dsarp.util import write_json                                        # noqa: E402
from dsarp.verification.openrewrite_loop import detect                   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--detector", default="designite",
                    help="designite is enough to enumerate smells and is much faster")
    ap.add_argument("--limit", type=int, default=8, help="max smells to ask about")
    ap.add_argument("--execute", action="store_true",
                    help="also RUN each validated proposal through the closed loop")
    args = ap.parse_args()

    cfg = load_config("local")
    repo_path = RepositoryManager(cfg.data_dir).path_for(args.repo)
    out = cfg.data_dir / "outputs" / args.repo

    model_cfg = dict(cfg.model_provider or {})
    provider = get_provider(model_cfg)
    print(f"[ai] model = {model_cfg.get('provider')}:{model_cfg.get('model')}")

    det = detect(repo_path, out / "ai_detect", args.detector)
    findings = det.get("findings", [])
    print(f"[ai] {det.get('smells')} smells detected")

    facts = SourceFacts(repo_path)
    routed = plan_all(repo_path, findings, facts)
    # Only ask about smells DSARP could NOT already handle — that is where an LLM could add
    # something, and it keeps the test honest rather than re-deriving known answers.
    gaps, seen = [], set()
    for p in routed["plans"]:
        if p.applicable or p.smell_type in seen:
            continue
        seen.add(p.smell_type)
        gaps.append({"smell_type": p.smell_type,
                     "components": p.components,
                     "description": p.reason})
    gaps = gaps[:args.limit]
    print(f"[ai] asking about {len(gaps)} smell type(s) DSARP cannot currently refactor: "
          f"{', '.join(g['smell_type'] for g in gaps)}\n")

    proposals, results = [], []
    for g in gaps:
        p = propose(provider, facts, g)
        proposals.append(p)
        if p.valid:
            recipes = ", ".join(e.recipe.rsplit(".", 1)[-1] for e in p.entries)
            print(f"  {g['smell_type']:28s} PROPOSED  {recipes}")
            print(f"  {'':28s}           {p.reasoning[:80]}")
        elif p.declined:
            print(f"  {g['smell_type']:28s} DECLINED  {p.reasoning[:78]}")
        else:
            print(f"  {g['smell_type']:28s} invalid   {p.rejection}")

    if args.execute:
        print()
        for p in proposals:
            if not p.valid:
                continue
            print(f"[ai] testing {p.smell_type} ...")
            r = test_proposal(cfg, args.repo, repo_path, p, detector=args.detector)
            results.append(r)
            print(f"      verdict={r['verdict']}  {r['why']}  (files={r['files_changed']})")

    valid = [p for p in proposals if p.valid]
    report = {
        "repo": args.repo, "model": f"{model_cfg.get('provider')}:{model_cfg.get('model')}",
        "smells_asked": len(gaps), "proposals_valid": len(valid),
        "proposals_declined": sum(1 for p in proposals if p.declined),
        "proposals_invalid": sum(1 for p in proposals if not p.valid and not p.declined),
        "proposals_rejected_before_running": len(proposals) - len(valid),
        "rejection_reasons": dict(collections.Counter(
            p.rejection for p in proposals if not p.valid)),
        "verdicts": dict(collections.Counter(r["verdict"] for r in results)),
        "proposals": [p.as_dict() for p in proposals],
        "test_results": results,
    }
    write_json(out / "ai_recipe_trials.json", report)

    print(f"\n[ai] valid {len(valid)}/{len(proposals)} proposals; "
          f"{report['proposals_rejected_before_running']} rejected before running")
    if results:
        print(f"[ai] verdicts: {report['verdicts']}")
    print(f"[ai] report -> {out / 'ai_recipe_trials.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
