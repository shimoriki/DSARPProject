"""Loop 13 — evaluation. Top-k recall vs historical refactorings + HGRS aggregation."""
from __future__ import annotations

from typing import Any, Dict, List

from ..mining.refactoring_miner import RefactoringEvent
from ..schemas import HGRSReview, Suggestion


class Evaluator:
    def topk_recall(self, suggestions: List[Suggestion],
                    historical: List[RefactoringEvent], k: int = 3) -> float:
        """Fraction of historical refactoring types recovered in top-k per smell component."""
        if not historical:
            return 0.0
        hist = {(e.refactoring_type, comp) for e in historical for comp in e.affected_components}
        top = suggestions[:k] if k else suggestions
        pred = {(s.recommended_refactoring, c.get("id"))
                for s in top for c in s.affected_components}
        hit = sum(1 for h in hist if h in pred)
        return round(hit / len(hist), 3) if hist else 0.0

    def aggregate_hgrs(self, reviews: List[HGRSReview]) -> Dict[str, Any]:
        if not reviews:
            return {"mean_hgrs": 0.0, "count": 0}
        for r in reviews:
            r.recompute()
        mean = sum(r.weighted_score for r in reviews) / len(reviews)
        return {
            "mean_hgrs": round(mean, 4),
            "count": len(reviews),
            "would_try_rate": round(sum(1 for r in reviews if r.would_try_it) / len(reviews), 3),
            "hallucination_flag_count": sum(len(r.hallucination_flags) for r in reviews),
        }
