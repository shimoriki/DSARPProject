"""Import the real Tika tool exports from the 'provided evidence' folder,
build normalized evidence, split, and generate scored suggestions ready for
human HGRS review.

Files used (architecture-level evidence):
  smell-characteristics.csv   Arcan architectural smells (cyclicDep, hubLike...)
  ArchitectureSmells.csv      Designite architecture smells (Package,Smell,Description)
  component-metrics.csv       Arcan per-package metrics (FanIn/FanOut/Instability/LOC)
  tika_static_graph.csv       class-level static dependencies (kept as raw edge evidence)

Deliberately not auto-imported (class/method-level; import manually if wanted):
  DesignSmells.csv, ImplementationSmells.csv, TestSmells.csv,
  TestabilitySmells.csv, MethodMetrics.csv, TypeMetrics.csv,
  tika_class_coverage_by_module.csv, smell-affects.csv (header is misaligned;
  its affected-element info already exists in smell-characteristics.csv).

Usage:
  py scripts/import_provided_evidence.py
  py scripts/import_provided_evidence.py --model-provider ollama --model-id qwen2.5-coder:7b
  py scripts/import_provided_evidence.py --modes baseline,skill,tool_evidence
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dsarp import services  # noqa: E402

IMPORTS = [
    ("arcan", "smell-characteristics.csv"),
    ("arcan", "component-metrics.csv"),
    ("designite", "ArchitectureSmells.csv"),
    ("static_graph", "tika_static_graph.csv"),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="provided evidence")
    parser.add_argument("--project", default="tika")
    parser.add_argument("--model-provider", default="mock")
    parser.add_argument("--model-id", default="mock")
    parser.add_argument("--modes", default="tool_evidence",
                        help="comma-separated agent modes to run")
    args = parser.parse_args()

    ctx = services.init_context(root_dir=ROOT)
    evidence_dir = ROOT / args.dir

    print(f"== 1. project '{args.project}' ==")
    services.add_project(ctx, args.project, architecture_type="package-based-java")

    print(f"== 2. import evidence from {evidence_dir} ==")
    for tool, fname in IMPORTS:
        path = evidence_dir / fname
        if not path.exists():
            print(f"   SKIP {fname} (not found)")
            continue
        s = services.import_tool_file(ctx, args.project, tool, str(path))
        print(f"   {tool:13s} {fname}: {s['smells']} smells, "
              f"{s['edges']} edges, {s['metrics']} metrics")

    print("== 3. build normalized evidence ==")
    n = services.rebuild_evidence(ctx, args.project)
    cases = ctx.store.list_cases(project_id=args.project)
    by_type: dict[str, int] = {}
    for c in cases:
        by_type[c["smell_type"]] = by_type.get(c["smell_type"], 0) + 1
    print(f"   {n} cases: " + ", ".join(f"{k}={v}" for k, v in sorted(by_type.items())))

    print("== 4. train/validation split ==")
    print(f"   {services.split_evidence(ctx, args.project)}")

    print(f"== 5. suggestions + suggested HGRS scores "
          f"({args.model_provider}:{args.model_id}) ==")
    for mode in [m.strip() for m in args.modes.split(",")]:
        runs = services.run_agents(ctx, args.project, mode,
                                   provider_name=args.model_provider,
                                   model_id=args.model_id)
        ok = sum(1 for r in runs if r["status"] == "ok")
        print(f"   {mode}: {ok}/{len(runs)} valid, scored runs")

    print("\nDone. Open the console to review and rate the base skill:")
    print("  streamlit run ui/app.py  ->  5 · Human Review")
    print("Every step above is recorded on page 9 · Activity Log.")


if __name__ == "__main__":
    main()
