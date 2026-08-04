"""Loop 6 — align smell evidence with historical refactorings (confidence-scored)."""
import argparse
import _bootstrap  # noqa: F401
from dsarp.alignment.aligner import SmellRefactoringAligner
from dsarp.config import load_config, load_repo_list
from dsarp.mining.refactoring_miner import RefactoringEvent
from dsarp.repositories.manager import slug_to_dirname
from dsarp.schemas import EvidenceCase
from dsarp.util import read_json, write_json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="local")
    ap.add_argument("--config", default="train")
    args = ap.parse_args()
    cfg = load_config(args.profile)
    kind = args.config.replace("configs/repos_", "").replace(".yaml", "")
    aligner = SmellRefactoringAligner()
    for slug in load_repo_list(kind):
        rid = slug_to_dirname(slug)
        case_data = read_json(cfg.data_dir / "normalized" / f"{rid}.json")
        if not case_data:
            continue
        case = EvidenceCase(**case_data)
        events = [RefactoringEvent(**e) for e in
                  (read_json(cfg.data_dir / "refactoring_events" / f"{rid}.json", default=[]) or [])]
        aligns = aligner.align(case.smells, events)
        write_json(cfg.data_dir / "aligned_examples" / f"{rid}.json",
                   [a.__dict__ for a in aligns])
        print(f"{rid}: {len(aligns)} alignments")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
