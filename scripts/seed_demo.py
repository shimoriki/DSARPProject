"""Reproducible Apache Tika demonstration - fully offline (mock provider).

Creates the tika project, imports the sample Arcan/Designite/graph exports,
builds evidence, assigns splits, runs all three agent modes with the mock
provider, and adds a couple of example human reviews so every console page
has content. Safe to re-run.

Usage:  py scripts/seed_demo.py [--model-provider ollama --model-id qwen2.5-coder:7b]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dsarp import services  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-provider", default="mock")
    parser.add_argument("--model-id", default="mock")
    args = parser.parse_args()

    ctx = services.init_context(root_dir=ROOT)

    print("== 1. project add ==")
    project = services.add_project(
        ctx, "tika-sample", architecture_type="package-based-java", source_revision="main")
    print(f"   project: {project['name']} ({project['id']})")

    print("== 2. import tool exports ==")
    imports = [
        ("arcan", "sample_data/tika/arcan/ArchitectureSmells.csv"),
        ("arcan", "sample_data/tika/arcan/DependencyEdges.csv"),
        ("designite", "sample_data/tika/designite/ArchitectureSmells.csv"),
        ("static_graph", "sample_data/tika/graph/edges.csv"),
    ]
    for tool, path in imports:
        summary = services.import_tool_file(ctx, "tika-sample", tool, path)
        print(f"   {tool}: {summary['smells']} smells, {summary['edges']} edges "
              f"from {Path(path).name}")

    print("== 3. build evidence ==")
    n = services.rebuild_evidence(ctx, "tika-sample")
    print(f"   {n} normalized evidence cases")

    print("== 4. split train/validation ==")
    counts = services.split_evidence(ctx, "tika-sample")
    print(f"   {counts}")

    print("== 5. run agents (baseline / skill / tool_evidence) ==")
    for mode in ("baseline", "skill", "tool_evidence"):
        runs = services.run_agents(ctx, "tika-sample", mode,
                                   provider_name=args.model_provider,
                                   model_id=args.model_id)
        ok = sum(1 for r in runs if r["status"] == "ok")
        print(f"   {mode}: {ok}/{len(runs)} valid runs")

    print("== 6. example human reviews (edit them in the console!) ==")
    reviewed = 0
    for run in ctx.store.list_runs(project_id="tika-sample", agent_mode="tool_evidence"):
        if run["status"] != "ok" or reviewed >= 2:
            continue
        if ctx.store.review_for_run(run["run_id"]):
            continue
        suggested = ctx.store.get_suggested_scores(run["run_id"]).get("deterministic", {})
        scores = {c: v["score"] for c, v in suggested.items()}
        review = services.save_review(
            ctx, run["run_id"], scores, "maybe", "revise",
            reviewer_notes="Seeded example review from scripts/seed_demo.py - "
                           "replace with a real human judgment in the console.")
        print(f"   review {review.review_id[:8]} HGRS={review.hgrs}")
        reviewed += 1

    print("\nDemo ready. Next:")
    print("  streamlit run ui/app.py")
    print("  py -m dsarp.cli experiment compare --project tika-sample   (after pip install -e .)")


if __name__ == "__main__":
    main()


