"""Loops 2-3 — import/execute RefactoringMiner events for configured repos."""
import argparse
import _bootstrap  # noqa: F401
from dsarp.config import load_config, load_repo_list
from dsarp.mining.refactoring_miner import RefactoringMinerAdapter
from dsarp.repositories.manager import slug_to_dirname
from dsarp.util import write_json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="local")
    ap.add_argument("--config", default="train")
    args = ap.parse_args()
    cfg = load_config(args.profile)
    kind = args.config.replace("configs/repos_", "").replace(".yaml", "")
    adapter = RefactoringMinerAdapter()
    for slug in load_repo_list(kind):
        rid = slug_to_dirname(slug)
        export = cfg.data_dir / "raw" / "refactoringminer" / f"{rid}.json"
        events = adapter.import_events(export) if export.exists() else []
        write_json(cfg.data_dir / "refactoring_events" / f"{rid}.json",
                   [e.to_dict() for e in events])
        print(f"{rid}: {len(events)} refactoring events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
