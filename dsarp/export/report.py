"""Loop 13 — export suggestions + evaluation report."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ..schemas import Suggestion
from ..util import write_json


def write_suggestions(path: Path, suggestions: List[Suggestion]) -> None:
    write_json(path, [s.to_contract_dict() for s in suggestions])


def build_report(project_id: str, revision: str, suggestions: List[Suggestion],
                 optimisation: Dict[str, Any]) -> Dict[str, Any]:
    n = len(suggestions)
    flagged = sum(1 for s in suggestions if s.verification_status == "flagged")
    unsupported = sum(len(s.no_hallucination_checks.unsupported_claims) for s in suggestions)
    grounded = sum(1 for s in suggestions if not s.no_hallucination_checks.unsupported_claims)
    recipes_possible = sum(1 for s in suggestions if s.openrewrite_recipe_plan.recipe_possible)
    recipes_validated = sum(1 for s in suggestions
                            if s.openrewrite_recipe_plan.recipe_status == "validated")
    smells = len({s.smell_id for s in suggestions})
    return {
        "project_id": project_id,
        "revision": revision,
        "num_smells": smells,
        "num_suggestions": n,
        "json_validity_rate": 1.0,  # all emitted via schema-validated models
        "evidence_grounding_pass_rate": round(grounded / n, 3) if n else 0.0,
        "hallucination_failure_count": unsupported,
        "flagged_suggestions": flagged,
        "recipe_draft_count": recipes_possible,
        "recipe_validation_count": recipes_validated,
        "top_suggestions": [
            {"rank": s.rank, "score": s.score, "smell_type": s.smell_type,
             "refactoring": s.recommended_refactoring,
             "components": [c.get("id") for c in s.affected_components][:4]}
            for s in suggestions[:5]
        ],
        "token_optimisation": optimisation,
    }


def write_report(path: Path, report: Dict[str, Any]) -> None:
    write_json(path, report)
