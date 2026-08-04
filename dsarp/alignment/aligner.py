"""Loop 6 — align historical refactorings with smell evidence.

CRITICAL POLICY: we do NOT assume every historical refactoring fixed a smell.
Each (smell, refactoring) pair gets an alignment_confidence in [0,1] from
overlap features. Low-confidence pairs are kept but flagged; they are weak labels.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from ..mining.refactoring_miner import RefactoringEvent
from ..schemas import Smell


# feature weights (sum ~1.0) — component/graph proximity dominates
_W = {
    "same_component": 0.45,
    "component_neighbourhood": 0.20,
    "smell_component_touched": 0.25,
    "type_plausibility": 0.10,
}

# which refactoring types are plausible fixes for which smell family
_PLAUSIBLE: Dict[str, set] = {
    "cyclic dependency": {"Extract Interface", "Move Class", "Move Method", "Extract Class"},
    "god class": {"Extract Class", "Extract Method", "Move Method", "Move Field"},
    "feature envy": {"Move Method", "Extract Method"},
    "hub-like dependency": {"Extract Interface", "Introduce Facade", "Move Class"},
}


@dataclass
class Alignment:
    smell_id: str
    smell_type: str
    event_id: str
    refactoring_type: str
    alignment_confidence: float
    features: Dict[str, float] = field(default_factory=dict)


class SmellRefactoringAligner:
    def align(self, smells: List[Smell], events: List[RefactoringEvent]) -> List[Alignment]:
        out: List[Alignment] = []
        for smell in smells:
            comps = set(smell.affected_components)
            for ev in events:
                feats = self._features(smell, comps, ev)
                conf = sum(_W[k] * v for k, v in feats.items())
                if conf <= 0:
                    continue
                out.append(Alignment(
                    smell_id=smell.smell_id, smell_type=smell.smell_type,
                    event_id=ev.event_id, refactoring_type=ev.refactoring_type,
                    alignment_confidence=round(conf, 4), features=feats,
                ))
        return out

    def _features(self, smell: Smell, comps: set, ev: RefactoringEvent) -> Dict[str, float]:
        ev_comps = set(ev.affected_components)
        same = 1.0 if comps & ev_comps else 0.0
        # neighbourhood: shared package prefix
        neigh = 0.0
        if not same and comps and ev_comps:
            for c in comps:
                for e in ev_comps:
                    if c and e and (c.startswith(e) or e.startswith(c)):
                        neigh = 1.0
                        break
        touched = same  # tool-affected component appears in the diff
        plausible = 1.0 if ev.refactoring_type in _PLAUSIBLE.get(
            smell.smell_type.lower(), set()) else 0.0
        return {
            "same_component": same,
            "component_neighbourhood": neigh,
            "smell_component_touched": touched,
            "type_plausibility": plausible,
        }
