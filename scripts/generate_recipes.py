"""Loop 11 — (re)generate OpenRewrite recipe drafts for a repo's suggestions."""
import argparse
import _bootstrap  # noqa: F401
from dsarp.candidates.generator import Candidate
from dsarp.config import load_config
from dsarp.openrewrite.generator import OpenRewriteGenerator
from dsarp.util import read_json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="local")
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    cfg = load_config(args.profile)
    sugs = read_json(cfg.data_dir / "outputs" / args.repo / "suggestions.json", default=[]) or []
    gen = OpenRewriteGenerator(cfg.data_dir / "outputs" / "recipes")
    n = 0
    for s in sugs:
        b = s.get("target_boundary", {})
        cand = Candidate(
            candidate_id=s["suggestion_id"], smell_id=s["smell_id"], smell_type=s["smell_type"],
            refactoring_type=s["refactoring_type"], recommended_refactoring=s["recommended_refactoring"],
            affected_components=[a.get("id") for a in s.get("affected_components", [])],
            target_boundary={"from": b.get("from", ""), "to": b.get("to", ""),
                             "edge_direction_status": b.get("edge_direction_status", "")},
            graph_delta_estimate=0.0, risk_score=0.0, recipe_applicable=True)
        plan, _ = gen.plan(cand)
        n += 1 if plan["recipe_possible"] else 0
    print(f"{args.repo}: {n} recipe-possible / {len(sugs)} suggestions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
