"""Loop 4/6 — normalize heterogeneous tool findings + graph into one EvidenceCase.

Merges findings that describe the same smell on the same components across tools
(tool agreement raises confidence). Produces the schema-valid EvidenceCase that the
candidate generator and ranker consume.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from ..schemas import DependencyGraph, EvidenceCase, Smell, SourceIndex
from ..tools.base import ToolFinding
from ..util import evidence_id


class EvidenceNormalizer:
    def normalize(
        self,
        project_id: str,
        revision: str,
        findings: List[ToolFinding],
        graph: DependencyGraph,
        source_index: SourceIndex | None = None,
    ) -> EvidenceCase:
        merged: Dict[Tuple[str, Tuple[str, ...]], Smell] = {}
        for f in findings:
            f.ensure_id()
            key = (f.smell_type.strip().lower(), tuple(sorted(f.affected_components)))
            if key in merged:
                s = merged[key]
                if f.tool not in s.tool_sources:
                    s.tool_sources.append(f.tool)
                if f.evidence_id not in s.evidence_ids:
                    s.evidence_ids.append(f.evidence_id)
            else:
                merged[key] = Smell(
                    smell_id=evidence_id("SMELL", project_id, f.smell_type, *f.affected_components),
                    smell_type=f.smell_type,
                    component_level=f.component_level,
                    affected_components=list(f.affected_components),
                    metrics=dict(f.metrics),
                    evidence_ids=[f.evidence_id],
                    tool_sources=[f.tool],
                    severity=f.severity,
                )
        # Graph-derived smells: cycles that no tool reported still count as evidence.
        for cyc in graph.graph_metrics.get("cycles", [])[:50]:
            if len(cyc) < 2:
                continue
            key = ("cyclic dependency", tuple(sorted(cyc)))
            if key in merged:
                s = merged[key]
                if "DependencyGraph" not in s.tool_sources:
                    s.tool_sources.append("DependencyGraph")
            else:
                merged[key] = Smell(
                    smell_id=evidence_id("SMELL", project_id, "Cyclic Dependency", *cyc),
                    smell_type="Cyclic Dependency", component_level="package",
                    affected_components=list(cyc),
                    metrics={"cycle_length": len(cyc)},
                    evidence_ids=[evidence_id("EVID", "DependencyGraph", "cycle", *cyc)],
                    tool_sources=["DependencyGraph"], severity="high",
                )
        return EvidenceCase(
            project_id=project_id, revision=revision,
            smells=list(merged.values()), dependency_graph=graph,
            source_index=source_index or SourceIndex(),
        )
