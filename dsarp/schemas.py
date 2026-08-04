"""Unified Pydantic schemas — the only objects that cross module boundaries.

Mirrors docs/schemas/*.json. Kept permissive (extra fields allowed) so the
pipeline never silently drops evidence, but the required contract is enforced.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Enums-as-constants (kept as plain str for schema-compat + forward safety)
# --------------------------------------------------------------------------- #
REFACTORING_TYPES = [
    "Move Method", "Move Class", "Extract Interface", "Dependency Inversion",
    "Introduce Facade", "Introduce Adapter", "Extract Class", "Extract Method",
    "OpenRewrite Recipe", "Other",
]
EDGE_STATUS = ["supported_by_evidence", "requires_source_inspection"]


def _uuid() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- #
# Evidence case (pipeline input)
# --------------------------------------------------------------------------- #
class Smell(BaseModel):
    smell_id: str
    smell_type: str
    component_level: str = "package"  # package | class | method
    affected_components: List[str] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    evidence_ids: List[str] = Field(default_factory=list)
    tool_sources: List[str] = Field(default_factory=list)
    severity: Optional[str] = None
    limitations: List[str] = Field(default_factory=list)


class GraphNode(BaseModel):
    id: str
    kind: str = "package"  # package | class
    metrics: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: float = 1.0
    kind: str = "depends_on"
    evidence_id: Optional[str] = None


class DependencyGraph(BaseModel):
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    graph_metrics: Dict[str, Any] = Field(default_factory=dict)


class SourceIndex(BaseModel):
    files: List[str] = Field(default_factory=list)
    classes: List[str] = Field(default_factory=list)
    methods: List[str] = Field(default_factory=list)


class EvidenceCase(BaseModel):
    case_id: str = Field(default_factory=_uuid)
    project_id: str
    revision: str
    architecture_type: str = "package-based-java"
    smells: List[Smell] = Field(default_factory=list)
    dependency_graph: DependencyGraph = Field(default_factory=DependencyGraph)
    source_index: SourceIndex = Field(default_factory=SourceIndex)


# --------------------------------------------------------------------------- #
# Suggestion (pipeline output) — mirrors docs/schemas/suggestion_schema.json
# --------------------------------------------------------------------------- #
class TargetBoundary(BaseModel):
    from_: str = Field(default="", alias="from")
    to: str = ""
    edge_direction_status: str = "requires_source_inspection"

    model_config = {"populate_by_name": True}


class OpenRewritePlan(BaseModel):
    recipe_possible: bool = False
    recipe_type: str = "Not applicable"  # YAML | Java visitor | Composite | Not applicable
    recipe_status: str = "not_applicable"  # draft|generated|validated|failed|not_applicable
    recipe_path: str = ""
    required_manual_steps: List[str] = Field(default_factory=list)


class ExpectedImpact(BaseModel):
    smell_removed: str = "unknown"  # yes | partial | unknown
    cycle_reduction: float = 0
    coupling_reduction_estimate: float = 0.0
    risk_level: str = "medium"  # low | medium | high


class Verification(BaseModel):
    source_checked: bool = False
    openrewrite_dry_run: str = "not_run"
    build: str = "not_run"
    tests: str = "not_run"
    graph_reanalysis: str = "not_run"


class NoHallucinationChecks(BaseModel):
    all_files_exist: bool = True
    all_entities_exist: bool = True
    all_edges_supported: bool = True
    unsupported_claims: List[str] = Field(default_factory=list)


class Suggestion(BaseModel):
    suggestion_id: str = Field(default_factory=_uuid)
    case_id: str
    project_id: str
    revision: str
    rank: int = 1
    score: float = 0.0
    confidence: float = 0.0
    smell_id: str
    smell_type: str
    recommended_refactoring: str
    refactoring_type: str = "Other"
    evidence_used: List[str] = Field(default_factory=list)
    affected_components: List[Dict[str, Any]] = Field(default_factory=list)
    target_entities: List[Dict[str, Any]] = Field(default_factory=list)
    target_boundary: TargetBoundary = Field(default_factory=TargetBoundary)
    reasoning: str = ""
    implementation_plan: List[str] = Field(default_factory=list)
    openrewrite_recipe_plan: OpenRewritePlan = Field(default_factory=OpenRewritePlan)
    expected_impact: ExpectedImpact = Field(default_factory=ExpectedImpact)
    verification: Verification = Field(default_factory=Verification)
    no_hallucination_checks: NoHallucinationChecks = Field(default_factory=NoHallucinationChecks)
    # edge_direction_status surfaced top-level too (output contract in CLAUDE.md)
    edge_direction_status: str = "requires_source_inspection"
    verification_status: str = "unverified"
    limitations: List[str] = Field(default_factory=list)
    # score component breakdown for the "Why This Rank?" UI (schema allows extras)
    rank_breakdown: Dict[str, float] = Field(default_factory=dict)
    tools_available: List[str] = Field(default_factory=list)
    tools_unavailable: List[str] = Field(default_factory=list)

    def to_contract_dict(self) -> Dict[str, Any]:
        return self.model_dump(by_alias=True)


# --------------------------------------------------------------------------- #
# Context package (token layer) — mirrors context_package_schema.json
# --------------------------------------------------------------------------- #
class TokenBudget(BaseModel):
    max_input_tokens: int = 6000
    max_output_tokens: int = 1200
    reserved_output_tokens: int = 1200


class EvidenceSlice(BaseModel):
    smell_ids: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    affected_components: List[str] = Field(default_factory=list)
    dependency_edges: List[Dict[str, Any]] = Field(default_factory=list)
    candidate_refactorings: List[Dict[str, Any]] = Field(default_factory=list)


class ExcludedContext(BaseModel):
    reason: str
    stored_at: str
    summary_ref: str = ""


class ContextPackage(BaseModel):
    context_package_id: str = Field(default_factory=_uuid)
    project_id: str
    revision: str
    task_type: str = "suggest_refactoring"
    token_budget: TokenBudget = Field(default_factory=TokenBudget)
    stable_context_refs: List[str] = Field(default_factory=list)
    project_memory_ref: str = ""
    evidence_slice: EvidenceSlice = Field(default_factory=EvidenceSlice)
    excluded_context: List[ExcludedContext] = Field(default_factory=list)
    source_inspection_requests: List[str] = Field(default_factory=list)
    cache_keys: Dict[str, str] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# HGRS human review — mirrors hgrs_review_schema.json
# --------------------------------------------------------------------------- #
HGRS_WEIGHTS = {
    "evidence_grounding": 0.25,
    "refactoring_relevance": 0.20,
    "architectural_reasoning": 0.15,
    "minimality_and_safety": 0.15,
    "actionability": 0.10,
    "human_confidence": 0.10,
    "cost_efficiency": 0.05,
}


class HGRSReview(BaseModel):
    review_id: str = Field(default_factory=_uuid)
    suggestion_id: str
    reviewer: str = "anonymous"
    scores: Dict[str, float] = Field(default_factory=dict)  # 0..1 per dimension
    weighted_score: float = 0.0
    would_try_it: bool = False
    preferred: bool = False
    hallucination_flags: List[str] = Field(default_factory=list)
    recipe_usefulness: Optional[str] = None
    notes: str = ""

    def recompute(self) -> "HGRSReview":
        total = sum(HGRS_WEIGHTS[k] * float(self.scores.get(k, 0.0)) for k in HGRS_WEIGHTS)
        self.weighted_score = round(total, 4)
        return self
