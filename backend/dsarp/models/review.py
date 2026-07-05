"""Human HGRS review schema. Humans can overwrite every suggested value."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class WouldTry(str, Enum):
    yes = "yes"
    maybe = "maybe"
    no = "no"


class Decision(str, Enum):
    accept = "accept"
    revise = "revise"
    reject = "reject"


class HumanReview(BaseModel):
    review_id: str
    run_id: str
    reviewer_id: str = "local_user"
    evidence_grounding: int = Field(ge=1, le=5)
    refactoring_relevance: int = Field(ge=1, le=5)
    architectural_reasoning: int = Field(ge=1, le=5)
    minimality_and_safety: int = Field(ge=1, le=5)
    actionability: int = Field(ge=1, le=5)
    human_confidence: int = Field(ge=1, le=5)
    cost_efficiency: int = Field(ge=1, le=5)
    hgrs: float = 0.0
    would_try_it: WouldTry = WouldTry.maybe
    decision: Decision = Decision.revise
    reviewer_notes: str = ""
    edited_output_json: Optional[str] = None  # human-edited preferred output
    review_timestamp: str

    def criterion_scores(self) -> dict[str, int]:
        return {
            "evidence_grounding": self.evidence_grounding,
            "refactoring_relevance": self.refactoring_relevance,
            "architectural_reasoning": self.architectural_reasoning,
            "minimality_and_safety": self.minimality_and_safety,
            "actionability": self.actionability,
            "human_confidence": self.human_confidence,
            "cost_efficiency": self.cost_efficiency,
        }
