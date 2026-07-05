"""Deterministic structural checks over an agent suggestion.

These produce (a) pass/fail check records, (b) suggested HGRS values that the
console shows as "Suggested system value — requires human confirmation", and
(c) a critical-hallucination flag used by the SkillOpt promotion gate.
Humans can always overwrite every suggested value.
"""
from __future__ import annotations

from typing import Any

from .models.evidence import EvidenceCase
from .models.suggestion import EdgeDirectionStatus, RefactoringSuggestion
from .store.repos import Store

# refactorings considered on-target per canonical smell (heuristic, editable)
RELEVANT_REFACTORINGS: dict[str, set[str]] = {
    "cyclic_dependency": {"Dependency Inversion", "Extract Interface", "Move Class",
                          "Move Method", "Split Component", "Facade", "Adapter"},
    "hub_like_dependency": {"Facade", "Split Component", "Extract Interface",
                            "Dependency Inversion"},
    "unstable_dependency": {"Dependency Inversion", "Extract Interface", "Adapter"},
    "god_component": {"Split Component", "Move Class", "Move Method"},
    "layer_violation": {"Dependency Inversion", "Move Class", "Adapter"},
    "feature_concentration": {"Split Component", "Move Class", "Move Method"},
    "microservice_bad_smell": {"Split Component", "Facade", "Adapter", "Other"},
}

_REASONING_TERMS = ("cycle", "direction", "boundary", "coupling", "stable",
                    "layer", "abstraction", "depend", "interface", "invert")


def _clamp(v: float) -> int:
    return int(max(1, min(5, round(v))))


def run_structural_checks(suggestion: RefactoringSuggestion, case: EvidenceCase,
                          run_record: dict, store: Store) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    known_ids = case.all_evidence_ids()
    known_components = set(case.affected_components)

    # --- evidence grounding ---
    used = suggestion.evidence_used
    unsupported_ids = sorted(set(used) - known_ids)
    checks.append({"name": "evidence_ids_exist",
                   "passed": not unsupported_ids and bool(used),
                   "detail": (f"unsupported ids: {unsupported_ids}" if unsupported_ids
                              else ("no evidence cited" if not used else "all cited ids exist"))})
    unknown_components = sorted(
        set(suggestion.affected_components) - known_components)
    checks.append({"name": "components_grounded",
                   "passed": not unknown_components,
                   "detail": (f"components not in evidence: {unknown_components}"
                              if unknown_components else "all components appear in evidence")})
    direction_ok = True
    boundary = suggestion.candidate_boundary_to_inspect
    if boundary.edge_direction_status == EdgeDirectionStatus.supported_by_evidence:
        pairs = case.edge_pairs()
        comps = boundary.components
        direction_ok = len(comps) >= 2 and any(
            (a, b) in pairs for a in comps for b in comps if a != b)
    checks.append({"name": "edge_direction_claim_supported",
                   "passed": direction_ok,
                   "detail": ("claimed supported_by_evidence but no imported edge covers "
                              "the boundary pair" if not direction_ok else "consistent")})

    grounding = 5.0
    if not used:
        grounding -= 2.0
    if used:
        grounding -= 4.0 * (len(unsupported_ids) / max(1, len(used)))
    if unknown_components:
        grounding -= 1.5
    if not direction_ok:
        grounding -= 2.0
    critical_hallucination = bool(unsupported_ids) or bool(unknown_components) or not direction_ok

    # --- refactoring relevance ---
    relevant = RELEVANT_REFACTORINGS.get(case.smell_key)
    rec = suggestion.recommended_refactoring.value
    relevance_ok = relevant is None or rec in relevant or rec == "Other"
    checks.append({"name": "refactoring_relevant_to_smell", "passed": relevance_ok,
                   "detail": f"'{rec}' for smell '{case.smell_key}'"})
    relevance = 4.0 if relevance_ok and rec != "Other" else (3.0 if relevance_ok else 2.0)

    # --- architectural reasoning (heuristic) ---
    rationale = (suggestion.rationale or "").lower()
    hits = sum(1 for t in _REASONING_TERMS if t in rationale)
    reasoning = 2.0 + min(2.0, hits * 0.5) + (0.5 if len(rationale) > 200 else 0.0)
    checks.append({"name": "rationale_mentions_architecture_concepts",
                   "passed": hits >= 2, "detail": f"{hits} architecture terms in rationale"})

    # --- minimality and safety ---
    has_risks = len(suggestion.risks_and_tradeoffs) >= 1
    step_count = len(suggestion.implementation_steps)
    checks.append({"name": "risks_and_tradeoffs_present", "passed": has_risks,
                   "detail": f"{len(suggestion.risks_and_tradeoffs)} risks listed"})
    minimality = 3.0 + (1.0 if has_risks else -1.5) + (0.5 if 3 <= step_count <= 7 else -0.5)

    # --- actionability ---
    concrete_steps = [s for s in suggestion.implementation_steps if len(s.strip()) > 15]
    named = sum(1 for s in concrete_steps
                if any(c in s for c in known_components))
    actionable = len(concrete_steps) >= 3
    checks.append({"name": "at_least_three_concrete_steps", "passed": actionable,
                   "detail": f"{len(concrete_steps)} concrete steps, {named} name components"})
    actionability = (4.0 if actionable else 2.0) + (0.5 if named >= 2 else 0.0)

    # --- human confidence: cannot be automated; neutral default ---
    human_confidence = 3.0

    # --- cost efficiency relative to other runs in the project ---
    stats = store.token_stats(case.project_id)
    totals = sorted(s["total_tokens"] for s in stats if s["total_tokens"])
    my_total = run_record.get("total_tokens") or 0
    if len(totals) >= 3 and my_total:
        rank = sum(1 for t in totals if t <= my_total) / len(totals)
        cost = 5.0 - 3.0 * rank  # cheapest -> ~5, most expensive -> ~2
    else:
        cost = 3.0
    checks.append({"name": "cost_relative_to_project_runs", "passed": True,
                   "detail": f"total_tokens={my_total}, compared against {len(totals)} runs"})

    suggested = {
        "evidence_grounding": {"score": _clamp(grounding),
                               "reason": checks[0]["detail"] + "; " + checks[1]["detail"]},
        "refactoring_relevance": {"score": _clamp(relevance),
                                  "reason": checks[3]["detail"]},
        "architectural_reasoning": {"score": _clamp(reasoning),
                                    "reason": checks[4]["detail"] + " (heuristic)"},
        "minimality_and_safety": {"score": _clamp(minimality),
                                  "reason": checks[5]["detail"]},
        "actionability": {"score": _clamp(actionability),
                          "reason": checks[6]["detail"]},
        "human_confidence": {"score": 3,
                             "reason": "Neutral default — only a human can judge this."},
        "cost_efficiency": {"score": _clamp(cost),
                            "reason": checks[7]["detail"]},
    }
    return {
        "checks": checks,
        "suggested_scores": suggested,
        "critical_hallucination": critical_hallucination,
        "unsupported_evidence_ids": unsupported_ids,
        "ungrounded_components": unknown_components,
    }
