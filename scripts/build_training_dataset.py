"""Loop 7 — build ranker dataset (candidates.jsonl) from aligned examples."""
import argparse
import _bootstrap  # noqa: F401
from dsarp.alignment.aligner import Alignment
from dsarp.config import load_config, load_repo_list
from dsarp.dataset.builder import DatasetBuilder
from dsarp.repositories.manager import slug_to_dirname
from dsarp.schemas import EvidenceCase
from dsarp.util import read_json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="local")
    ap.add_argument("--config", default="train")
    ap.add_argument("--large", action="store_true")
    args = ap.parse_args()
    cfg = load_config(args.profile)
    kind = args.config.replace("configs/repos_", "").replace(".yaml", "")
    builder = DatasetBuilder(cfg.data_dir / "training")
    total = []
    for slug in load_repo_list(kind):
        rid = slug_to_dirname(slug)
        case_data = read_json(cfg.data_dir / "normalized" / f"{rid}.json")
        if not case_data:
            continue
        case = EvidenceCase(**case_data)
        aligns = [Alignment(**a) for a in
                  (read_json(cfg.data_dir / "aligned_examples" / f"{rid}.json", default=[]) or [])]
        for smell in case.smells:
            rows = builder.build_ranker_rows(smell, case.dependency_graph, aligns)
            builder.write_ranker(rows)
            total.extend(rows)
    print("dataset:", builder.stats(total))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
