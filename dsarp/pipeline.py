"""Inference orchestration (Loops 9-13).

evidence case -> candidates -> rank -> explain (token-optimised) -> recipe plan
-> validate -> ranked Suggestions + token/optimisation report.

Repository-independent: no raw package names influence ranking (features are structural).
Source index (when present) powers real entity validation; when absent, unproven entities
become `requires_source_inspection` rather than hallucinations.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .agents.explainer import ExplanationAgent
from .cache import HashCache
from .candidates.generator import CandidateGenerator
from .config import Config
from .models.providers import get_provider
from .openrewrite.generator import OpenRewriteGenerator
from .ranking.ranker import PreferenceRanker
from .schemas import (EvidenceCase, ExpectedImpact, OpenRewritePlan, Suggestion,
                      TargetBoundary, TokenBudget, Verification)
from .source_index.indexer import SourceIndexer
from .tokens import TokenBudgetManager
from .util import read_json
from .validation.validators import ValidationEngine

SUGGESTION_SCHEMA = Path(__file__).resolve().parent.parent / "docs" / "schemas" / "suggestion_schema.json"


class InferencePipeline:
    def __init__(self, config: Config, top_k_per_smell: int = 3,
                 model_override: Optional[Dict[str, Any]] = None,
                 min_confidence: Optional[float] = None):
        self.config = config
        self.top_k = top_k_per_smell
        self.gate = dict(config.quality_gate)
        if min_confidence is not None:
            self.gate["min_confidence"] = min_confidence
        self.gen = CandidateGenerator()
        tb = TokenBudget(**config.token_budget)
        self.budget_mgr = TokenBudgetManager(
            tb, log_path=config.data_dir / "outputs" / "token_usage.jsonl")
        self.cache = HashCache(config.data_dir)
        # ranker: prefer data/models, fall back to legacy data/training
        ranker_path = config.data_dir / "models" / "ranker.pkl"
        if not ranker_path.exists():
            ranker_path = config.data_dir / "training" / "ranker.pkl"
        self.ranker = PreferenceRanker(ranker_path)
        provider_cfg = model_override or config.model_provider
        self.agent = ExplanationAgent(get_provider(provider_cfg), self.budget_mgr, self.cache)
        self.recipes = OpenRewriteGenerator(config.data_dir / "outputs" / "recipes")
        self.validator = ValidationEngine(SUGGESTION_SCHEMA)

    def _load_source_lookup(self, project_id: str) -> Tuple[Optional[Dict], bool]:
        idx = read_json(self.config.data_dir / "source_index" / f"{project_id}.json")
        if not idx:
            return None, False
        return SourceIndexer.build_lookup(idx), True

    def run(self, case: EvidenceCase, memory_ref: str = "") -> Tuple[List[Suggestion], Dict[str, Any]]:
        source_lookup, has_source = self._load_source_lookup(case.project_id)
        tools_available = sorted({t for s in case.smells for t in s.tool_sources})
        tools_unavailable = [t for t in ("Arcan", "Designite", "RefactoringMiner")
                             if t not in tools_available]
        suggestions: List[Suggestion] = []
        for smell in case.smells:
            candidates = self.gen.generate(smell, case.dependency_graph,
                                           source_inspection_available=has_source)
            ev_conf = min(1.0, 0.4 + 0.2 * len(smell.tool_sources))
            ranked = self.ranker.rank(candidates, ev_conf)[: self.top_k]
            for entry in ranked:
                cand = entry["candidate"]
                explanation = self.agent.explain(
                    case.project_id, case.revision, smell, cand, memory_ref)
                recipe_plan, _ = self.recipes.plan(cand)
                sug = self._to_suggestion(case, smell, cand, entry, explanation, recipe_plan)
                sug.tools_available = tools_available
                sug.tools_unavailable = tools_unavailable
                sug = self.validator.validate_suggestion(sug, case, source_lookup)
                suggestions.append(sug)
        # --- accuracy gate: keep only VALID, high-confidence, evidence-backed ---
        kept, dropped = self._apply_quality_gate(suggestions)
        kept.sort(key=lambda s: s.score, reverse=True)
        for i, s in enumerate(kept, 1):
            s.rank = i
        report = self._optimisation_report(case)
        report["ranker_metadata"] = self.ranker.metadata
        report["source_index_available"] = has_source
        report["quality_gate"] = {**self.gate, "emitted": len(kept),
                                   "dropped": dropped, "candidates_before_gate": len(suggestions)}
        return kept, report

    def _apply_quality_gate(self, suggestions):
        keep, dropped = [], 0
        for s in suggestions:
            nh = s.no_hallucination_checks
            valid = not nh.unsupported_claims
            has_ev = bool(s.evidence_used)
            ok = True
            if self.gate.get("require_valid", True) and not valid:
                ok = False
            if self.gate.get("require_evidence", True) and not has_ev:
                ok = False
            if s.confidence < float(self.gate.get("min_confidence", 0.0)):
                ok = False
            if ok:
                keep.append(s)
            else:
                dropped += 1
        return keep, dropped

    def _to_suggestion(self, case, smell, cand, entry, explanation, recipe_plan) -> Suggestion:
        b = cand.target_boundary
        return Suggestion(
            case_id=case.case_id, project_id=case.project_id, revision=case.revision,
            rank=entry["rank"], score=entry["score"], confidence=entry["confidence"],
            smell_id=smell.smell_id, smell_type=smell.smell_type,
            recommended_refactoring=cand.recommended_refactoring,
            refactoring_type=cand.refactoring_type,
            evidence_used=list(smell.evidence_ids),
            affected_components=[{"id": c, "level": smell.component_level}
                                 for c in smell.affected_components],
            target_boundary=TargetBoundary(**{
                "from": b.get("from", ""), "to": b.get("to", ""),
                "edge_direction_status": b.get("edge_direction_status",
                                               "requires_source_inspection")}),
            edge_direction_status=b.get("edge_direction_status", "requires_source_inspection"),
            reasoning=explanation.get("reasoning", ""),
            implementation_plan=recipe_plan.get("required_manual_steps", []),
            openrewrite_recipe_plan=OpenRewritePlan(**recipe_plan),
            expected_impact=ExpectedImpact(
                smell_removed="partial" if cand.graph_delta_estimate > 0.5 else "unknown",
                cycle_reduction=round(cand.graph_delta_estimate, 2),
                coupling_reduction_estimate=round(cand.graph_delta_estimate * 0.5, 3),
                risk_level=("low" if cand.risk_score < 0.35
                            else "high" if cand.risk_score > 0.6 else "medium")),
            verification=Verification(),
            limitations=["requires_source_inspection"] if cand.requires_source_inspection else [],
            rank_breakdown={
                "final": entry["score"], "graph_score": entry.get("deterministic", 0.0),
                "ranker_score": entry.get("learned", -1.0),
                "evidence_confidence": entry.get("evidence_confidence", 0.0),
                "risk": cand.risk_score, "graph_delta": cand.graph_delta_estimate,
            },
        )

    def _optimisation_report(self, case: EvidenceCase) -> Dict[str, Any]:
        s = self.budget_mgr.summary()
        return {
            "run_id": case.case_id,
            "project_id": case.project_id,
            "total_model_calls": s["total_model_calls"],
            "cache_hits": s["cache_hits"],
            "cache_misses": s["cache_misses"],
            "actual_prompt_tokens": s["actual_prompt_tokens"],
            "actual_completion_tokens": s["actual_completion_tokens"],
            "estimated_tokens_saved": s["cache_hits"] * self.budget_mgr.budget.max_input_tokens,
            "recommendations": [
                "Cache graph/tool summaries", "Reduce raw tool logs in prompts",
                "Use source snippets only after candidate selection",
            ],
        }
