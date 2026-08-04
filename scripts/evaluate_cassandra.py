"""Loop 13 — final unseen-test evaluation on apache/cassandra.

Guardrail: refuses to run if cassandra appears in any TRAINING config.
"""
import argparse
import _bootstrap  # noqa: F401
from dsarp.config import load_config, load_repo_list
from dsarp.evaluation.evaluator import Evaluator
from dsarp.export.report import build_report, write_report, write_suggestions
from dsarp.mining.refactoring_miner import RefactoringEvent
from dsarp.pipeline import InferencePipeline
from dsarp.schemas import EvidenceCase
from dsarp.util import read_json

TEST_REPO = "apache-cassandra"


def _guard() -> None:
    for kind in ("train", "validation"):
        if any("cassandra" in s for s in load_repo_list(kind)):
            raise SystemExit(f"GUARDRAIL: cassandra found in repos_{kind}.yaml — test leakage!")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="local")
    ap.add_argument("--top-k", type=int, default=3)
    args = ap.parse_args()
    _guard()
    cfg = load_config(args.profile)
    data = read_json(cfg.data_dir / "normalized" / f"{TEST_REPO}.json")
    if not data:
        print("no normalized cassandra evidence; run tools import + normalize first")
        return 1
    case = EvidenceCase(**data)
    sugs, opt = InferencePipeline(cfg, args.top_k).run(case)
    out = cfg.data_dir / "outputs" / TEST_REPO
    write_suggestions(out / "suggestions.json", sugs)
    report = build_report(case.project_id, case.revision, sugs, opt)

    hist = [RefactoringEvent(**e) for e in
            (read_json(cfg.data_dir / "refactoring_events" / f"{TEST_REPO}.json", default=[]) or [])]
    report["topk_recall_vs_history"] = Evaluator().topk_recall(sugs, hist, args.top_k)
    write_report(out / "report.json", report)
    print(f"Cassandra: {report['num_suggestions']} suggestions, "
          f"grounding={report['evidence_grounding_pass_rate']}, "
          f"hallucinations={report['hallucination_failure_count']}, "
          f"recall={report['topk_recall_vs_history']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
