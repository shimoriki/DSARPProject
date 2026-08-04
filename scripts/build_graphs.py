"""Loop 5 — build dependency graphs + compact summaries for configured repos."""
import argparse
import _bootstrap  # noqa: F401
from dsarp.config import load_config, load_repo_list
from dsarp.graphs.builder import DependencyGraphBuilder
from dsarp.memory import ProjectMemory
from dsarp.repositories.manager import slug_to_dirname
from dsarp.util import read_json, write_json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="local")
    ap.add_argument("--config", default="train")
    args = ap.parse_args()
    cfg = load_config(args.profile)
    kind = args.config.replace("configs/repos_", "").replace(".yaml", "")
    b = DependencyGraphBuilder()
    for slug in load_repo_list(kind):
        rid = slug_to_dirname(slug)
        edges = read_json(cfg.data_dir / "raw" / "graphs" / f"{rid}.json", default=[]) or []
        dg = b.build(edges)
        write_json(cfg.data_dir / "graphs" / f"{rid}.json", dg.model_dump())
        ProjectMemory(cfg.data_dir, rid).write_json("graph_summary.json", b.summary(dg))
        print(f"{rid}: {dg.graph_metrics.get('node_count')} nodes, "
              f"{dg.graph_metrics.get('cycle_count')} cycles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
