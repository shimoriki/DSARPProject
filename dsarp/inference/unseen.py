"""Addendum §5 — inference on ANY new / unseen repository.

Pipeline: clone-or-read -> detect build system -> source index -> dependency graph
(import-edge fallback if no tool graph) -> tool evidence (if available) -> normalize
-> candidates -> rank -> explain -> recipes -> validate -> report.

Works even when Arcan/Designite are unavailable by falling back to the source index +
import graph, and the report states exactly which tools were used vs unavailable.
Repository-independent throughout (no hardcoded package names).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..evidence.normalizer import EvidenceNormalizer
from ..graphs.builder import DependencyGraphBuilder
from ..memory import ProjectMemory
from ..pipeline import InferencePipeline
from ..repositories.manager import RepositoryManager
from ..schemas import EvidenceCase, SourceIndex, Suggestion
from ..source_index.indexer import SourceIndexer
from ..tools.base import ToolFinding
from ..util import read_json, write_json


def detect_build_system(repo_path: Path) -> str:
    repo_path = Path(repo_path)
    if (repo_path / "pom.xml").exists():
        return "maven"
    if (repo_path / "build.gradle").exists() or (repo_path / "build.gradle.kts").exists():
        return "gradle"
    if list(repo_path.glob("*.java")) or list(repo_path.rglob("*.java")):
        return "plain-java"
    return "unknown"


def _load_tool_findings(cfg: Config, project_id: str) -> Tuple[List[ToolFinding], List[str]]:
    findings: List[ToolFinding] = []
    used: List[str] = []
    for tool in ("arcan", "designite"):
        recs = read_json(cfg.data_dir / "raw" / tool / f"{project_id}.json", default=[]) or []
        if recs:
            used.append(tool)
            for r in recs:
                findings.append(ToolFinding(**r))
    return findings, used


def prepare_evidence(cfg: Config, project_id: str, repo_path: Optional[Path] = None,
                     repo_url: Optional[str] = None) -> Dict[str, Any]:
    """Build (and persist) a normalized EvidenceCase for an unseen repo."""
    rm = RepositoryManager(cfg.data_dir)
    if repo_url and not repo_path:
        rm.clone(project_id if "/" in project_id else project_id, url=repo_url)
        repo_path = rm.path_for(project_id)
    repo_path = Path(repo_path) if repo_path else rm.path_for(project_id)

    build_system = detect_build_system(repo_path)
    tools_unavailable: List[str] = []

    # 1) source index (best-effort; empty if repo not present locally)
    idx = SourceIndexer().index(project_id, repo_path)
    write_json(cfg.data_dir / "source_index" / f"{project_id}.json", idx.to_dict())

    # 2) dependency graph: prefer a staged tool graph, else source-index import edges
    staged_edges = read_json(cfg.data_dir / "raw" / "graphs" / f"{project_id}.json", default=None)
    if staged_edges:
        edges = staged_edges
        graph_source = "staged"
    elif idx.import_edges:
        edges = idx.import_edges
        graph_source = "source-index-imports"
    else:
        edges = read_json(cfg.data_dir / "graphs" / f"{project_id}.json", default={})
        edges = [{"source": e["source"], "target": e["target"]}
                 for e in (edges.get("edges", []) if isinstance(edges, dict) else [])]
        graph_source = "existing" if edges else "none"
    dg = DependencyGraphBuilder().build(edges)
    write_json(cfg.data_dir / "graphs" / f"{project_id}.json", dg.model_dump())
    ProjectMemory(cfg.data_dir, project_id).write_json(
        "graph_summary.json", DependencyGraphBuilder.summary(dg))

    # 3) tool findings (if imported) + tool-free STRUCTURAL smells (all types we can prove)
    findings, tools_used = _load_tool_findings(cfg, project_id)
    for t in ("Arcan", "Designite"):
        if t.lower() not in tools_used:
            tools_unavailable.append(t)
    from ..smells.detector import StructuralSmellDetector
    structural = StructuralSmellDetector().detect(project_id, dg, idx.to_dict())
    findings = list(findings) + structural

    case = EvidenceNormalizer().normalize(
        project_id, "HEAD", findings, dg, idx.to_source_index())
    write_json(cfg.data_dir / "normalized" / f"{project_id}.json", case.model_dump())
    return {
        "project_id": project_id, "build_system": build_system,
        "graph_source": graph_source, "smells": len(case.smells),
        "source_files": idx.file_count, "tools_used": tools_used,
        "tools_unavailable": tools_unavailable,
    }


def evaluate_unseen_repo(cfg: Config, project_id: str, repo_path: Optional[Path] = None,
                         repo_url: Optional[str] = None, top_k: int = 3,
                         model_override: Optional[Dict] = None) -> Tuple[List[Suggestion], Dict[str, Any]]:
    prep = prepare_evidence(cfg, project_id, repo_path, repo_url)
    case = EvidenceCase(**read_json(cfg.data_dir / "normalized" / f"{project_id}.json"))
    mem = ProjectMemory(cfg.data_dir, project_id)
    pipe = InferencePipeline(cfg, top_k_per_smell=top_k, model_override=model_override)
    suggestions, report = pipe.run(case, mem.memory_ref(case.revision))
    report["preparation"] = prep
    return suggestions, report
