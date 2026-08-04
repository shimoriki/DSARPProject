"""Stage sample tool exports into data/raw/ for a demo `suggest` run (offline).

Runs the same import path the CLI uses, so it exercises real adapters, not fakes.
Usage:  python scripts/make_sample_data.py [project_id]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dsarp.config import load_config  # noqa: E402
from dsarp.graphs.builder import DependencyGraphBuilder  # noqa: E402
from dsarp.memory import ProjectMemory  # noqa: E402
from dsarp.tools.arcan import ArcanAdapter  # noqa: E402
from dsarp.tools.designite import DesigniteAdapter  # noqa: E402
from dsarp.util import read_json, write_json  # noqa: E402

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "samples"


def main(project_id: str = "apache-cassandra") -> int:
    cfg = load_config("local")
    # 1) graph
    edges = read_json(SAMPLES / "cassandra_edges.json", default=[])
    dg = DependencyGraphBuilder().build(edges)
    write_json(cfg.data_dir / "graphs" / f"{project_id}.json", dg.model_dump())
    ProjectMemory(cfg.data_dir, project_id).write_json(
        "graph_summary.json", DependencyGraphBuilder.summary(dg))
    # 2) tool findings via real adapters
    arcan = ArcanAdapter().import_findings(SAMPLES / "cassandra_arcan.json")
    des = DesigniteAdapter().import_findings(SAMPLES / "cassandra_designite.csv")
    write_json(cfg.data_dir / "raw" / "arcan" / f"{project_id}.json", [f.__dict__ for f in arcan])
    write_json(cfg.data_dir / "raw" / "designite" / f"{project_id}.json", [f.__dict__ for f in des])
    print(f"[sample] staged {len(arcan)} arcan + {len(des)} designite findings, "
          f"{dg.graph_metrics['cycle_count']} cycles for {project_id}")
    print("[sample] next: dsarp-local normalize --repo", project_id,
          "&& dsarp-local suggest --repo", project_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "apache-cassandra"))
