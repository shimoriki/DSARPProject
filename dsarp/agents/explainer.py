"""Loop 10 — LLM explanation agent (token-optimised).

Builds a minimal context package (Level 0 stable refs + Level 2 evidence slice),
enforces the token budget, checks the cache, then asks the provider to explain a
ranked candidate. The LLM only *explains*; it never invents candidates or evidence.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..cache import HashCache
from ..candidates.generator import Candidate
from ..models.providers import ModelProvider
from ..schemas import ContextPackage, EvidenceSlice, Smell, TokenBudget
from ..tokens import TokenBudgetManager, UsageRecord

STABLE_REFS = ["NO_HALLUCINATION_POLICY_v1", "OUTPUT_SCHEMA_v1", "OPENREWRITE_POLICY_v1"]


class ExplanationAgent:
    def __init__(self, provider: ModelProvider, budget_mgr: TokenBudgetManager,
                 cache: Optional[HashCache] = None):
        self.provider = provider
        self.budget = budget_mgr
        self.cache = cache

    def build_context_package(self, project_id: str, revision: str, smell: Smell,
                              candidate: Candidate, project_memory_ref: str = "") -> ContextPackage:
        return ContextPackage(
            project_id=project_id, revision=revision, task_type="explain_candidate",
            token_budget=self.budget.budget, stable_context_refs=STABLE_REFS,
            project_memory_ref=project_memory_ref,
            evidence_slice=EvidenceSlice(
                smell_ids=[smell.smell_id], evidence_ids=list(smell.evidence_ids),
                affected_components=list(smell.affected_components),
                candidate_refactorings=[{
                    "type": candidate.refactoring_type,
                    "recommended": candidate.recommended_refactoring,
                    "graph_delta": candidate.graph_delta_estimate,
                    "risk": candidate.risk_score,
                }],
            ),
        )

    def _prompt(self, smell: Smell, candidate: Candidate) -> str:
        # Level 0 + Level 2 only. No raw graphs/logs (token policy).
        return (
            "You are an evidence-grounded refactoring explainer. Use ONLY the evidence below.\n"
            "Rules: cite evidence IDs; never claim a file/class/method/edge exists unless it is in "
            "the evidence; if unknown, say requires_source_inspection.\n\n"
            f"Smell: {smell.smell_type} (level={smell.component_level})\n"
            f"Affected components: {', '.join(smell.affected_components[:8])}\n"
            f"Evidence IDs: {', '.join(smell.evidence_ids[:8])}\n"
            f"Tool sources: {', '.join(smell.tool_sources)}\n"
            f"Proposed refactoring: {candidate.recommended_refactoring} "
            f"(graph_delta={candidate.graph_delta_estimate}, risk={candidate.risk_score})\n"
            f"Target boundary: {candidate.target_boundary}\n\n"
            "Write 3-5 sentences: why this refactoring addresses the smell, the concrete boundary "
            "to change, and any step that needs source inspection."
        )

    def explain(self, project_id: str, revision: str, smell: Smell,
                candidate: Candidate, project_memory_ref: str = "") -> Dict[str, Any]:
        prompt = self._prompt(smell, candidate)
        est_in = self.budget.check_prompt(prompt)

        cache_hit = False
        text = None
        cache_key = None
        if self.cache is not None:
            cache_key = self.cache.key("explain", self.provider.model, prompt)
            cached = self.cache.get("explain", cache_key)
            if cached is not None:
                text, cache_hit = cached["text"], True

        if text is None:
            resp = self.provider.generate(prompt, max_tokens=self.budget.budget.max_output_tokens)
            text = resp.text
            prompt_tok, completion_tok = resp.prompt_tokens, resp.completion_tokens
            if self.cache is not None and cache_key is not None:
                self.cache.put("explain", cache_key, {"text": text})
        else:
            prompt_tok = completion_tok = None

        self.budget.log(UsageRecord(
            task_type="explain_candidate", model_id=self.provider.model,
            input_token_estimate=est_in,
            output_token_estimate=self.budget.budget.max_output_tokens,
            actual_prompt_tokens=prompt_tok, actual_completion_tokens=completion_tok,
            cache_hit=cache_hit, evidence_ids_used=list(smell.evidence_ids),
        ))
        return {"reasoning": text, "cache_hit": cache_hit}
