"""Repository-independent structural features + name masking (addendum §2).

The ranker must NOT learn from raw package/class names (org.apache.tika.*). This
module converts a (smell, candidate, graph) into a purely structural feature vector
and masks names to Component_A/B/C for training. Real names are restored only at
explanation time.
"""
from __future__ import annotations

import string
from dataclasses import dataclass
from typing import Any, Dict, List

from ..schemas import DependencyGraph, Smell

FEATURE_SCHEMA_VERSION = "1.0"

# Canonical, ordered, repo-independent feature vector consumed by the ranker.
FEATURE_ORDER: List[str] = [
    "cycle_size", "fan_in", "fan_out", "instability", "centrality",
    "coupling", "cohesion", "atdi", "severity", "tool_agreement_count",
    "edge_confidence", "candidate_refactoring_code", "component_role_code",
    "component_type_code", "estimated_edges_removed", "estimated_edges_added",
    "affected_component_count", "recipe_applicability", "source_inspection_available",
    "public_api_risk", "graph_delta", "risk", "catalogue_rank",
]

_SEVERITY = {"high": 1.0, "medium": 0.6, "low": 0.3, "": 0.6}
_REFAC_CODE = {
    "Extract Interface": 1, "Dependency Inversion": 2, "Introduce Facade": 3,
    "Introduce Adapter": 4, "Move Class": 5, "Move Method": 6,
    "Extract Class": 7, "Extract Method": 8, "Split Package": 9, "Merge Package": 10,
    "Introduce Parameter Object": 11, "Move Field": 12,
}
_ROLE_CODE = {"hub": 1, "unstable": 2, "cyclic": 3, "god": 4, "envy": 5, "generic": 0}
_TYPE_CODE = {"package": 1, "class": 2, "method": 3}
# refactorings that touch public API surface (higher automation risk)
_PUBLIC_API = {"Extract Interface", "Move Class", "Move Method", "Dependency Inversion"}


class NameMasker:
    """Deterministic component-name masking for one case. Reversible."""

    def __init__(self, components: List[str]):
        self.forward: Dict[str, str] = {}
        self.reverse: Dict[str, str] = {}
        for i, comp in enumerate(dict.fromkeys(components)):  # stable, de-duped
            token = f"Component_{self._label(i)}"
            self.forward[comp] = token
            self.reverse[token] = comp

    @staticmethod
    def _label(i: int) -> str:
        # A..Z, then AA, AB, ...
        letters = string.ascii_uppercase
        if i < 26:
            return letters[i]
        return letters[i // 26 - 1] + letters[i % 26]

    def mask(self, text: str) -> str:
        if not text:
            return text
        for real, token in self.forward.items():
            text = text.replace(real, token)
        return text

    def unmask(self, text: str) -> str:
        if not text:
            return text
        for token, real in self.reverse.items():
            text = text.replace(token, real)
        return text

    def mask_component(self, comp: str) -> str:
        return self.forward.get(comp, comp)


@dataclass
class _CandidateView:
    refactoring_type: str
    recommended_refactoring: str
    graph_delta_estimate: float
    risk_score: float
    recipe_applicable: bool
    requires_source_inspection: bool
    catalogue_rank: float = 0.5


class FeatureExtractor:
    def _component_role(self, smell: Smell, avg: Dict[str, float]) -> str:
        st = smell.smell_type.lower()
        if "hub" in st:
            return "hub"
        if "unstable" in st:
            return "unstable"
        if "cyclic" in st:
            return "cyclic"
        if "god" in st:
            return "god"
        if "envy" in st:
            return "envy"
        if avg.get("instability", 0) > 0.7:
            return "unstable"
        if avg.get("fan_in", 0) > 5:
            return "hub"
        return "generic"

    def _avg_node_metrics(self, smell: Smell, graph: DependencyGraph) -> Dict[str, float]:
        by_id = {n.id: n.metrics for n in graph.nodes}
        comps = [c for c in smell.affected_components if c in by_id]
        if not comps:
            return {"fan_in": 0.0, "fan_out": 0.0, "instability": 0.0,
                    "centrality": 0.0, "coupling": 0.0}
        fi = sum(by_id[c].get("fan_in", 0) for c in comps) / len(comps)
        fo = sum(by_id[c].get("fan_out", 0) for c in comps) / len(comps)
        inst = sum(by_id[c].get("instability", 0.0) for c in comps) / len(comps)
        cen = sum(by_id[c].get("betweenness", 0.0) for c in comps) / len(comps)
        return {"fan_in": fi, "fan_out": fo, "instability": inst,
                "centrality": cen, "coupling": fi + fo}

    def extract(self, smell: Smell, candidate: Any, graph: DependencyGraph,
                source_inspection_available: bool = False,
                edge_supported: bool = False) -> Dict[str, float]:
        c = candidate  # duck-typed: has refactoring fields
        avg = self._avg_node_metrics(smell, graph)
        cycle_size = float(smell.metrics.get("cycle_length", 0) or
                           (len(smell.affected_components) if "cyclic" in smell.smell_type.lower() else 0))
        role = self._component_role(smell, avg)
        delta = float(getattr(c, "graph_delta_estimate", 0.0))
        risk = float(getattr(c, "risk_score", 0.5))
        rtype = getattr(c, "recommended_refactoring", getattr(c, "refactoring_type", "Other"))
        return {
            "cycle_size": cycle_size,
            "fan_in": round(avg["fan_in"], 3),
            "fan_out": round(avg["fan_out"], 3),
            "instability": round(avg["instability"], 3),
            "centrality": round(avg["centrality"], 4),
            "coupling": round(avg["coupling"], 3),
            "cohesion": 0.0,  # not available without deeper source parse -> flagged
            "atdi": float(smell.metrics.get("ATDI", 0.0) or 0.0),
            "severity": _SEVERITY.get((smell.severity or "medium").lower(), 0.6),
            "tool_agreement_count": float(len(smell.tool_sources)),
            "edge_confidence": 1.0 if edge_supported else 0.5,
            "candidate_refactoring_code": float(_REFAC_CODE.get(rtype, 0)),
            "component_role_code": float(_ROLE_CODE.get(role, 0)),
            "component_type_code": float(_TYPE_CODE.get(smell.component_level, 1)),
            "estimated_edges_removed": round(delta * max(1.0, cycle_size), 3),
            "estimated_edges_added": 1.0 if rtype in ("Extract Interface", "Introduce Facade",
                                                      "Introduce Adapter") else 0.0,
            "affected_component_count": float(len(smell.affected_components)),
            "recipe_applicability": 1.0 if getattr(c, "recipe_applicable", False) else 0.0,
            "source_inspection_available": 1.0 if source_inspection_available else 0.0,
            "public_api_risk": round((0.7 if rtype in _PUBLIC_API else 0.3) * (0.5 + risk / 2), 3),
            "graph_delta": round(delta, 3),
            "risk": round(risk, 3),
            "catalogue_rank": round(float(getattr(c, "catalogue_rank", 0.5)), 3),
        }

    @staticmethod
    def vector(features: Dict[str, float]) -> List[float]:
        return [float(features.get(k, 0.0)) for k in FEATURE_ORDER]
