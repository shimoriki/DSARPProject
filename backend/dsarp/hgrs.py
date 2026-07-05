"""HGRS rubric: criteria, weights, and score computation."""
from __future__ import annotations

from typing import Mapping

CRITERIA: list[str] = [
    "evidence_grounding",
    "refactoring_relevance",
    "architectural_reasoning",
    "minimality_and_safety",
    "actionability",
    "human_confidence",
    "cost_efficiency",
]

DEFAULT_WEIGHTS: dict[str, float] = {
    "evidence_grounding": 0.25,
    "refactoring_relevance": 0.20,
    "architectural_reasoning": 0.15,
    "minimality_and_safety": 0.15,
    "actionability": 0.10,
    "human_confidence": 0.10,
    "cost_efficiency": 0.05,
}

CRITERION_LABELS: dict[str, str] = {
    "evidence_grounding": "Evidence Grounding",
    "refactoring_relevance": "Refactoring Relevance",
    "architectural_reasoning": "Architectural Reasoning",
    "minimality_and_safety": "Minimality and Safety",
    "actionability": "Actionability",
    "human_confidence": "Human Confidence",
    "cost_efficiency": "Cost Efficiency",
}


def validate_weights(weights: Mapping[str, float]) -> dict[str, float]:
    missing = [c for c in CRITERIA if c not in weights]
    if missing:
        raise ValueError(f"HGRS weights missing criteria: {missing}")
    total = sum(float(weights[c]) for c in CRITERIA)
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"HGRS weights must sum to 1.0, got {total}")
    return {c: float(weights[c]) for c in CRITERIA}


def compute_hgrs(scores: Mapping[str, int | float], weights: Mapping[str, float] | None = None) -> float:
    """Weighted HGRS from seven 1-5 criterion scores."""
    w = validate_weights(weights or DEFAULT_WEIGHTS)
    for c in CRITERIA:
        if c not in scores:
            raise ValueError(f"missing HGRS criterion: {c}")
        v = float(scores[c])
        if not 1.0 <= v <= 5.0:
            raise ValueError(f"criterion {c} out of range 1-5: {v}")
    return round(sum(w[c] * float(scores[c]) for c in CRITERIA), 3)
