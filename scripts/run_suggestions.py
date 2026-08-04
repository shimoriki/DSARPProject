"""Loops 9-13 — run the inference pipeline for a repo and write outputs."""
import argparse
import _bootstrap  # noqa: F401
from dsarp.config import load_config
from dsarp.export.report import build_report, write_report, write_suggestions
from dsarp.memory import ProjectMemory
from dsarp.pipeline import InferencePipeline
from dsarp.schemas import EvidenceCase
from dsarp.util import read_json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="local")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--top-k", type=int, default=3)
    args = ap.parse_args()
    cfg = load_config(args.profile)
    data = read_json(cfg.data_dir / "normalized" / f"{args.repo}.json")
    if not data:
        print("no normalized evidence; run normalize first")
        return 1
    case = EvidenceCase(**data)
    mem = ProjectMemory(cfg.data_dir, args.repo)
    sugs, opt = InferencePipeline(cfg, args.top_k).run(case, mem.memory_ref(case.revision))
    out = cfg.data_dir / "outputs" / args.repo
    write_suggestions(out / "suggestions.json", sugs)
    write_report(out / "report.json", build_report(case.project_id, case.revision, sugs, opt))
    print(f"{args.repo}: {len(sugs)} suggestions, cache_hits={opt['cache_hits']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
