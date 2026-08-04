"""Loop 10 (part 1) — deterministic candidate generation.

The LLM must NOT invent the candidate space. For each smell we enumerate a fixed
catalogue of refactorings keyed by smell family, compute a graph-delta estimate,
risk and recipe applicability from graph evidence only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import networkx as nx

from ..features.extractor import FeatureExtractor
from ..graphs.builder import DependencyGraphBuilder
from ..schemas import DependencyGraph, Smell
from ..util import evidence_id

# smell family -> ordered candidate refactorings (refactoring_type from schema enum)
CATALOGUE: Dict[str, List[str]] = {
    "cyclic dependency": [
        "Extract Interface", "Dependency Inversion", "Introduce Facade",
        "Introduce Adapter", "Move Class", "Move Method",
    ],
    "god class": ["Extract Class", "Extract Method", "Move Method"],
    "god component": ["Extract Class", "Move Class", "Move Method", "Introduce Facade"],
    "feature envy": ["Move Method", "Extract Method"],
    "hub-like dependency": ["Extract Interface", "Introduce Facade", "Move Class"],
    "unstable dependency": ["Dependency Inversion", "Extract Interface"],
    "layer violation": ["Dependency Inversion", "Extract Interface", "Move Class"],
    # Designite architectural smells
    "feature concentration": ["Extract Class", "Split Package", "Move Class"],
    "scattered functionality": ["Move Class", "Introduce Facade", "Extract Class"],
    "dense structure": ["Introduce Facade", "Dependency Inversion", "Extract Interface"],
}
# free-text refactorings not in the schema enum map to "Other"
_ENUM = {
    "Move Method", "Move Class", "Extract Interface", "Dependency Inversion",
    "Introduce Facade", "Introduce Adapter", "Extract Class", "Extract Method",
}


@dataclass
class Candidate:
    candidate_id: str
    smell_id: str
    smell_type: str
    refactoring_type: str          # schema enum value
    recommended_refactoring: str   # human phrasing
    affected_components: List[str]
    target_boundary: Dict[str, str]
    graph_delta_estimate: float    # expected cycle/coupling reduction (0..1)
    risk_score: float              # 0 (safe) .. 1 (risky)
    recipe_applicable: bool
    evidence_ids: List[str] = field(default_factory=list)
    requires_source_inspection: bool = True
    catalogue_rank: float = 0.5
    features: Dict[str, float] = field(default_factory=dict)


class CandidateGenerator:
    def __init__(self):
        self._fx = FeatureExtractor()

    def generate(self, smell: Smell, graph: DependencyGraph,
                 source_inspection_available: bool = False) -> List[Candidate]:
        family = smell.smell_type.strip().lower()
        catalogue = CATALOGUE.get(family, ["Extract Interface", "Move Class"])
        g = DependencyGraphBuilder.to_networkx(graph)
        boundary = self._pick_boundary(smell, g)
        edge_supported = boundary.get("edge_direction_status") == "supported_by_evidence"
        out: List[Candidate] = []
        for i, rtype in enumerate(catalogue):
            delta = self._graph_delta(rtype, smell, g)
            risk = self._risk(rtype)
            enum_type = rtype if rtype in _ENUM else "Other"
            cand = Candidate(
                candidate_id=evidence_id("CAND", smell.smell_id, rtype),
                smell_id=smell.smell_id, smell_type=smell.smell_type,
                refactoring_type=enum_type, recommended_refactoring=rtype,
                affected_components=list(smell.affected_components),
                target_boundary=boundary,
                graph_delta_estimate=round(delta, 4), risk_score=round(risk, 4),
                recipe_applicable=rtype in {"Move Class", "Extract Interface"},
                evidence_ids=list(smell.evidence_ids),
                requires_source_inspection=not source_inspection_available,
                catalogue_rank=round(1.0 - i / max(1, len(catalogue)), 4),
            )
            # repo-independent structural feature vector (no raw names).
            cand.features = self._fx.extract(
                smell, cand, graph,
                source_inspection_available=source_inspection_available,
                edge_supported=edge_supported)
            out.append(cand)
        return out

    def _pick_boundary(self, smell: Smell, g: nx.DiGraph) -> Dict[str, str]:
        comps = smell.affected_components
        if len(comps) >= 2:
            src, tgt = comps[0], comps[1]
            status = ("supported_by_evidence"
                      if g.has_edge(src, tgt) or g.has_edge(tgt, src)
                      else "requires_source_inspection")
            return {"from": src, "to": tgt, "edge_direction_status": status}
        one = comps[0] if comps else ""
        return {"from": one, "to": "", "edge_direction_status": "requires_source_inspection"}

    def _graph_delta(self, rtype: str, smell: Smell, g: nx.DiGraph) -> float:
        # estimate: breaking an edge in a cycle reduces cycles; interfaces/inversion help most
        base = {"Extract Interface": 0.7, "Dependency Inversion": 0.75,
                "Introduce Facade": 0.5, "Introduce Adapter": 0.45,
                "Move Class": 0.4, "Move Method": 0.35,
                "Extract Class": 0.5, "Extract Method": 0.3}.get(rtype, 0.3)
        cyc_bonus = 0.15 if "cyclic" in smell.smell_type.lower() else 0.0
        return min(1.0, base + cyc_bonus)

    def _risk(self, rtype: str) -> float:
        return {"Extract Interface": 0.2, "Dependency Inversion": 0.5,
                "Introduce Facade": 0.35, "Introduce Adapter": 0.35,
                "Move Class": 0.4, "Move Method": 0.45,
                "Extract Class": 0.55, "Extract Method": 0.3}.get(rtype, 0.5)
