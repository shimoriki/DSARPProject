"""Weak-supervised alignment for REAL repos without RefactoringMiner history.

RefactoringMiner gives *historical* refactoring labels; those need the JVM tool.
When it is unavailable we still get a real, honest training signal from the real
dependency graph: a candidate refactoring is weakly-positive if it is a known fix
for the detected smell AND the smell is graph-evidenced (e.g. a real cycle it can
break). Confidence is deliberately capped below the historical-label confidence so
the ranker treats these as weaker evidence.

This is weak supervision, NOT a claim that the refactoring was ever applied — so it
never fabricates history. Rows built from it are marked source="graph_weak".
"""
from __future__ import annotations

from typing import List

from ..alignment.aligner import Alignment
from ..schemas import DependencyGraph, Smell

# Only the STRONGEST fix per smell family is weakly-labelled positive (highest
# graph-delta / lowest risk). The generator still emits the full candidate catalogue,
# so the weaker alternatives become NEGATIVES — giving the ranker a real preference
# signal (both classes) instead of an all-positive degenerate label set.
_CYCLE_BREAKERS = {"Extract Interface", "Dependency Inversion"}
_HUB_FIXERS = {"Extract Interface"}
_UNSTABLE_FIXERS = {"Dependency Inversion"}
_GOD_FIXERS = {"Extract Class"}

# weak labels are capped so historical (real RefactoringMiner) labels dominate
WEAK_MAX = 0.6


class GraphWeakAligner:
    def align(self, smells: List[Smell], graph: DependencyGraph) -> List[Alignment]:
        cycles = graph.graph_metrics.get("cycles", []) or []
        node_metrics = {n.id: n.metrics for n in graph.nodes}
        out: List[Alignment] = []
        for smell in smells:
            fixers, base = self._fixers_for(smell)
            if not fixers:
                continue
            # is the smell backed by a REAL graph structure it can act on?
            support = self._graph_support(smell, cycles, node_metrics)
            if support <= 0:
                continue
            conf = min(WEAK_MAX, base * support)
            for rt in fixers:
                out.append(Alignment(
                    smell_id=smell.smell_id, smell_type=smell.smell_type,
                    event_id=f"WEAK_{smell.smell_id}_{rt.replace(' ', '')}",
                    refactoring_type=rt, alignment_confidence=round(conf, 4),
                    features={"weak": 1.0, "graph_support": round(support, 3)}))
        return out

    def _fixers_for(self, smell: Smell):
        st = smell.smell_type.lower()
        if "cyclic" in st:
            return _CYCLE_BREAKERS, 0.9
        if "hub" in st:
            return _HUB_FIXERS, 0.7
        if "unstable" in st:
            return _UNSTABLE_FIXERS, 0.7
        if "god" in st:
            return _GOD_FIXERS, 0.7
        return set(), 0.0

    def _graph_support(self, smell: Smell, cycles, node_metrics) -> float:
        comps = set(smell.affected_components)
        st = smell.smell_type.lower()
        if "cyclic" in st:
            # supported if the affected components actually lie on a detected cycle
            for cyc in cycles:
                if comps & set(cyc):
                    return 1.0
            return 0.5 if smell.metrics.get("cycle_length") else 0.0
        if "hub" in st:
            fan = max((node_metrics.get(c, {}).get("fan_in", 0)
                       + node_metrics.get(c, {}).get("fan_out", 0) for c in comps), default=0)
            return min(1.0, fan / 8.0)
        if "unstable" in st:
            inst = max((node_metrics.get(c, {}).get("instability", 0.0) for c in comps), default=0.0)
            return inst
        if "god" in st:
            cc = smell.metrics.get("class_count", 0)
            return min(1.0, cc / 40.0) if cc else 0.5
        return 0.0
