"""Optional critic agent: proposes HGRS values for the console to PRE-FILL.

The critic never replaces human scores; its output is stored under source
'critic' in suggested_scores and always labeled as requiring confirmation.
"""
from __future__ import annotations

import json

from ..hgrs import CRITERIA
from ..log import get_logger
from ..models.evidence import EvidenceCase
from ..providers.base import ModelProvider, ProviderError
from ..store.repos import Store
from .runner import extract_json

log = get_logger("critic")

_SYSTEM = """You are a strict reviewer of architectural refactoring suggestions.
Score the suggestion on seven criteria, each an integer 1-5.
Respond with ONLY a JSON object of the form:
{"evidence_grounding": {"score": 3, "reason": "..."}, ...}
Criteria: evidence_grounding, refactoring_relevance, architectural_reasoning,
minimality_and_safety, actionability, human_confidence, cost_efficiency.
Judge grounding only against the evidence in the case. Be conservative."""


def run_critic(store: Store, provider: ModelProvider, run_id: str,
               case: EvidenceCase, suggestion_json: str) -> dict | None:
    user = (
        "BEGIN_CRITIC_TASK\n"
        "Evidence case:\nBEGIN_CASE_JSON\n"
        + json.dumps(case.public_dict(), indent=2)
        + "\nEND_CASE_JSON\n\nSuggestion to review:\n"
        + suggestion_json
        + "\nEND_CRITIC_TASK\nReturn the scores JSON now.")
    try:
        result = provider.chat(_SYSTEM, user)
        payload = json.loads(extract_json(result.text))
    except (ProviderError, ValueError, json.JSONDecodeError) as exc:
        log.warning("critic failed for run %s: %s", run_id, exc)
        return None
    scores: dict = {}
    for c in CRITERIA:
        entry = payload.get(c)
        if isinstance(entry, dict) and "score" in entry:
            score = int(max(1, min(5, int(entry["score"]))))
            scores[c] = {"score": score, "reason": str(entry.get("reason", ""))[:500]}
        elif isinstance(entry, (int, float)):
            scores[c] = {"score": int(max(1, min(5, int(entry)))), "reason": ""}
    if len(scores) != len(CRITERIA):
        log.warning("critic returned incomplete criteria for run %s", run_id)
        return None
    store.save_suggested_scores(run_id, "critic", scores)
    return scores
