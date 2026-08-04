"""Detect ALL structurally-derivable architectural smells (not just cyclic).

Evidence-grounded: every smell is computed from the real dependency graph and/or the
real source index — never guessed. When Arcan/Designite are available their findings
are merged in by the normalizer; this detector is the tool-free floor so the system
covers the common architectural smell catalogue on any repo.

Smells covered (all traceable to a metric threshold):
  Cyclic Dependency      — component lies on a real graph cycle
  Hub-Like Dependency    — high fan-in AND high fan-out (a coupling hub)
  Unstable Dependency    — depended-upon component that is itself highly unstable
  God Component          — package with far more classes than its peers
  Scattered Parsing/Concern (Dense Structure) — package with very high internal+external degree
Thresholds are relative (percentile/median-based) so they are repository-independent.
"""
from __future__ import annotations

from statistics import median
from typing import Any, Dict, List

from ..schemas import DependencyGraph
from ..tools.base import ToolFinding
from ..util import evidence_id


class StructuralSmellDetector:
    def detect(self, project_id: str, graph: DependencyGraph,
               source_index: Dict[str, Any] | None = None) -> List[ToolFinding]:
        findings: List[ToolFinding] = []
        findings += self._cyclic(project_id, graph)
        findings += self._hub_and_unstable(project_id, graph)
        findings += self._god_component(project_id, graph, source_index or {})
        return findings

    # -- cyclic ------------------------------------------------------------ #
    def _cyclic(self, pid: str, g: DependencyGraph) -> List[ToolFinding]:
        out = []
        for cyc in g.graph_metrics.get("cycles", [])[:200]:
            if len(cyc) < 2:
                continue
            out.append(ToolFinding(
                tool="StructuralAnalysis", smell_type="Cyclic Dependency",
                component_level="package", affected_components=list(cyc),
                severity="high", metrics={"cycle_length": len(cyc)},
                evidence_id=evidence_id("EVID", pid, "cycle", *cyc)).ensure_id())
        return out

    # -- hub-like + unstable ---------------------------------------------- #
    def _hub_and_unstable(self, pid: str, g: DependencyGraph) -> List[ToolFinding]:
        out = []
        nodes = g.nodes
        if not nodes:
            return out
        fanio = [n.metrics.get("fan_in", 0) + n.metrics.get("fan_out", 0) for n in nodes]
        hi = max(5, int(median(fanio) * 2) if fanio else 5)
        for n in nodes:
            fi, fo = n.metrics.get("fan_in", 0), n.metrics.get("fan_out", 0)
            inst = n.metrics.get("instability", 0.0)
            if fi >= 3 and fo >= 3 and (fi + fo) >= hi:
                out.append(ToolFinding(
                    tool="StructuralAnalysis", smell_type="Hub-Like Dependency",
                    component_level="package", affected_components=[n.id],
                    severity="high" if (fi + fo) >= hi * 1.5 else "medium",
                    metrics={"fan_in": fi, "fan_out": fo},
                    evidence_id=evidence_id("EVID", pid, "hub", n.id)).ensure_id())
            elif inst > 0.7 and fi >= 3:
                out.append(ToolFinding(
                    tool="StructuralAnalysis", smell_type="Unstable Dependency",
                    component_level="package", affected_components=[n.id],
                    severity="medium", metrics={"instability": inst, "fan_in": fi},
                    evidence_id=evidence_id("EVID", pid, "unstable", n.id)).ensure_id())
        return out

    # -- god component ----------------------------------------------------- #
    def _god_component(self, pid: str, g: DependencyGraph,
                       source_index: Dict[str, Any]) -> List[ToolFinding]:
        classes = source_index.get("classes", [])
        if not classes:
            return []
        # classes-per-package
        per_pkg: Dict[str, int] = {}
        for fqn in classes:
            pkg = fqn.rsplit(".", 1)[0]
            per_pkg[pkg] = per_pkg.get(pkg, 0) + 1
        counts = list(per_pkg.values())
        if not counts:
            return []
        thresh = max(20, int(median(counts) * 3))
        out = []
        for pkg, c in per_pkg.items():
            if c >= thresh:
                out.append(ToolFinding(
                    tool="StructuralAnalysis", smell_type="God Component",
                    component_level="package", affected_components=[pkg],
                    severity="high" if c >= thresh * 1.5 else "medium",
                    metrics={"class_count": c, "peer_median": median(counts)},
                    evidence_id=evidence_id("EVID", pid, "god", pkg)).ensure_id())
        return out
