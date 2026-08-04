"""Generate synthetic multi-repository fixtures (normalized evidence + alignments).

Creates repo-independent training material for several TRAIN repos with DISTINCT
package namespaces, so multi-repo dataset building and generalisation can be
demonstrated offline without cloning or JVM tools. Cassandra is never generated here.

Usage: python scripts/make_multi_repo_fixtures.py
"""
from __future__ import annotations

import _bootstrap  # noqa: F401
from dsarp.alignment.aligner import SmellRefactoringAligner
from dsarp.config import load_config
from dsarp.evidence.normalizer import EvidenceNormalizer
from dsarp.graphs.builder import DependencyGraphBuilder
from dsarp.memory import ProjectMemory
from dsarp.mining.refactoring_miner import RefactoringEvent
from dsarp.tools.base import ToolFinding
from dsarp.util import write_json

# project_id -> (package_root, module names). Distinct roots => no name leakage.
REPOS = {
    "apache-tika":   ("org.apache.tika",   ["parser", "detect", "metadata", "mime", "sax"]),
    "apache-struts": ("org.apache.struts2", ["dispatcher", "views", "interceptor", "config"]),
    "apache-log4j2": ("org.apache.logging.log4j", ["core", "appender", "layout", "config"]),
    "google-guava":  ("com.google.common", ["collect", "cache", "graph", "io"]),
}


def _edges(root: str, mods):
    e = []
    # chain + a cycle between first two modules
    for i in range(len(mods) - 1):
        e.append({"source": f"{root}.{mods[i]}", "target": f"{root}.{mods[i+1]}", "weight": 3})
    e.append({"source": f"{root}.{mods[1]}", "target": f"{root}.{mods[0]}", "weight": 2})  # cycle
    return e


def build_repo(cfg, pid, root, mods):
    edges = _edges(root, mods)
    dg = DependencyGraphBuilder().build(edges)
    write_json(cfg.data_dir / "graphs" / f"{pid}.json", dg.model_dump())
    ProjectMemory(cfg.data_dir, pid).write_json(
        "graph_summary.json", DependencyGraphBuilder.summary(dg))

    a, b, c = f"{root}.{mods[0]}", f"{root}.{mods[1]}", f"{root}.{mods[2]}"
    findings = [
        ToolFinding("Arcan", "Cyclic Dependency", "package", [a, b], "high").ensure_id(),
        ToolFinding("Designite", "Cyclic Dependency", "package", [a, b], "high").ensure_id(),
        ToolFinding("Designite", "God Component", "package", [c], "medium").ensure_id(),
    ]
    write_json(cfg.data_dir / "raw" / "arcan" / f"{pid}.json", [f.__dict__ for f in findings[:1]])
    write_json(cfg.data_dir / "raw" / "designite" / f"{pid}.json",
               [f.__dict__ for f in findings[1:]])

    case = EvidenceNormalizer().normalize(pid, "fixture-sha", findings, dg)
    write_json(cfg.data_dir / "normalized" / f"{pid}.json", case.model_dump())

    # historical refactorings that plausibly fixed the cyclic smell
    events = [
        RefactoringEvent(f"REF_{pid}_1", "fixture-sha", "Extract Interface",
                         affected_components=[a, b]),
        RefactoringEvent(f"REF_{pid}_2", "fixture-sha", "Move Class",
                         affected_components=[a]),
    ]
    write_json(cfg.data_dir / "refactoring_events" / f"{pid}.json",
               [e.to_dict() for e in events])
    aligns = SmellRefactoringAligner().align(case.smells, events)
    write_json(cfg.data_dir / "aligned_examples" / f"{pid}.json", [a.__dict__ for a in aligns])
    return len(case.smells), len(aligns)


def main() -> int:
    cfg = load_config("local")
    for pid, (root, mods) in REPOS.items():
        s, a = build_repo(cfg, pid, root, mods)
        print(f"[fixture] {pid}: {s} smells, {a} alignments (root={root})")
    print("[fixture] next: dsarp-local dataset build-multi-repo && dsarp-local train ranker ...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
