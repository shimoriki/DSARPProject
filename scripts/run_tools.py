"""Loop 4 — run/import Arcan & Designite evidence for repos.

Import mode (default): parse tool exports found under data/raw/<tool>/exports/<repo>/.
Execute mode (HPC): calls adapter.execute() (JVM CLI wiring lives in the adapters).
"""
import argparse
from pathlib import Path

import _bootstrap  # noqa: F401
from dsarp.config import load_config, load_repo_list
from dsarp.repositories.manager import RepositoryManager, slug_to_dirname
from dsarp.tools.arcan import ArcanAdapter
from dsarp.tools.designite import DesigniteAdapter
from dsarp.util import write_json

ADAPTERS = {"arcan": ArcanAdapter, "designite": DesigniteAdapter}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="local")
    ap.add_argument("--config", default="train")
    ap.add_argument("--tools", default="arcan,designite")
    ap.add_argument("--mode", default="import", choices=["import", "execute"])
    args = ap.parse_args()
    cfg = load_config(args.profile)
    rm = RepositoryManager(cfg.data_dir)
    kind = args.config.replace("configs/repos_", "").replace(".yaml", "")
    for slug in load_repo_list(kind):
        rid = slug_to_dirname(slug)
        for tool in args.tools.split(","):
            tool = tool.strip()
            if tool not in ADAPTERS:
                continue
            adapter = ADAPTERS[tool]()
            if args.mode == "execute":
                findings = adapter.execute(rm.path_for(slug), "HEAD",
                                           cfg.data_dir / "raw" / tool)
            else:
                exports = cfg.data_dir / "raw" / tool / "exports" / rid
                findings = adapter.import_findings(exports) if exports.exists() else []
            write_json(cfg.data_dir / "raw" / tool / f"{rid}.json",
                       [f.__dict__ for f in findings])
            print(f"{rid}/{tool}: {len(findings)} findings ({args.mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
