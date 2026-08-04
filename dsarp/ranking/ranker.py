"""Loop 8/10 (part 2) — preference ranker (repo-independent features).

Two backends behind one interface:
  - deterministic weighted score (always available, no training) — MVP default
  - learned model (scikit-learn / LightGBM) loaded from disk if trained & present

Final score fuses: deterministic graph score + learned score + evidence confidence.
Features come from dsarp.features (structural, no raw names) so the ranker generalises
across repositories. The LLM critic can nudge but never reorders past validators.
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..candidates.generator import Candidate
from ..features.extractor import FEATURE_ORDER  # re-exported for scripts_support

# deterministic weights over a subset of structural features (risk terms negative)
_DET_W = {
    "graph_delta": 0.30,
    "estimated_edges_removed": 0.12,
    "severity": 0.14,
    "tool_agreement_count": 0.06,     # 0..N, squashed below
    "catalogue_rank": 0.12,
    "instability": 0.06,
    "edge_confidence": 0.06,
    "risk": -0.18,
    "public_api_risk": -0.10,
}


def _sig(x: float) -> float:
    return 1.0 / (1.0 + pow(2.718281828, -4 * (x - 0.2)))


class PreferenceRanker:
    def __init__(self, model_path: Optional[Path] = None):
        self.model = None
        self.metadata: Dict[str, Any] = {}
        self.model_path = Path(model_path) if model_path else None
        if self.model_path and self.model_path.exists():
            try:
                with open(self.model_path, "rb") as fh:
                    obj = pickle.load(fh)
                if isinstance(obj, dict) and "model" in obj:
                    self.model, self.metadata = obj["model"], obj.get("metadata", {})
                else:
                    self.model = obj
            except Exception:
                self.model = None

    def _det_score(self, c: Candidate) -> float:
        f = c.features
        s = 0.0
        for k, w in _DET_W.items():
            v = f.get(k, 0.0)
            if k == "tool_agreement_count":
                v = min(1.0, v / 3.0)
            s += w * v
        return _sig(s)

    def _learned_score(self, c: Candidate) -> Optional[float]:
        if self.model is None:
            return None
        x = [[c.features.get(k, 0.0) for k in FEATURE_ORDER]]
        try:
            if hasattr(self.model, "predict_proba"):
                return float(self.model.predict_proba(x)[0][-1])
            return float(self.model.predict(x)[0])
        except Exception:
            return None

    def score(self, c: Candidate, evidence_confidence: float = 0.6) -> Dict[str, float]:
        det = self._det_score(c)
        learned = self._learned_score(c)
        if learned is None:
            fused = 0.7 * det + 0.3 * evidence_confidence
        else:
            fused = 0.4 * det + 0.4 * learned + 0.2 * evidence_confidence
        return {"score": round(fused, 4), "deterministic": round(det, 4),
                "learned": round(learned, 4) if learned is not None else -1.0,
                "evidence_confidence": round(evidence_confidence, 4)}

    def rank(self, candidates: List[Candidate], evidence_confidence: float = 0.6) -> List[Dict[str, Any]]:
        scored = []
        for c in candidates:
            sc = self.score(c, evidence_confidence)
            scored.append({"candidate": c, **sc})
        scored.sort(key=lambda d: d["score"], reverse=True)
        for i, d in enumerate(scored, 1):
            d["rank"] = i
            d["confidence"] = round(min(1.0, d["score"] * (0.5 + 0.5 * c_conf(d["candidate"]))), 4)
        return scored


def c_conf(c: Candidate) -> float:
    """Confidence proxy: more tool agreement + lower risk => higher."""
    agree = min(1.0, c.features.get("tool_agreement_count", 0.0) / 3.0)
    return max(0.0, min(1.0, agree * 0.6 + (1.0 - c.features.get("risk", 0.5)) * 0.4))
