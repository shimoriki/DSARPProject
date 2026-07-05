"""Agent output schema. Strictly validated; malformed outputs stored separately."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AgentMode(str, Enum):
    baseline = "baseline"
    skill = "skill"
    tool_evidence = "tool_evidence"


class EdgeDirectionStatus(str, Enum):
    supported_by_evidence = "supported_by_evidence"
    requires_source_inspection = "requires_source_inspection"


class RefactoringType(str, Enum):
    extract_interface = "Extract Interface"
    dependency_inversion = "Dependency Inversion"
    move_class = "Move Class"
    move_method = "Move Method"
    facade = "Facade"
    adapter = "Adapter"
    split_component = "Split Component"
    other = "Other"


class CandidateBoundary(BaseModel):
    components: list[str] = Field(default_factory=list)
    edge_direction_status: EdgeDirectionStatus = EdgeDirectionStatus.requires_source_inspection
    reason: str = ""


class RefactoringSuggestion(BaseModel):
    run_id: str
    project_id: str
    smell_id: str
    smell_type: str
    agent_mode: AgentMode
    model_id: str
    skill_version: str = "none"
    evidence_used: list[str] = Field(default_factory=list)
    observed_tool_evidence: list[str] = Field(default_factory=list)
    candidate_boundary_to_inspect: CandidateBoundary = Field(default_factory=CandidateBoundary)
    recommended_refactoring: RefactoringType
    rationale: str
    implementation_steps: list[str] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)
    risks_and_tradeoffs: list[str] = Field(default_factory=list)
    assumptions_and_questions: list[str] = Field(default_factory=list)
    expected_benefit: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    limitations: str = ""


# Fields the model must produce itself; everything else is stamped by the
# runner from authoritative run metadata and never trusted from model output.
MODEL_OWNED_FIELDS: tuple = (
    "evidence_used", "observed_tool_evidence", "candidate_boundary_to_inspect",
    "recommended_refactoring", "rationale", "implementation_steps",
    "affected_components", "risks_and_tradeoffs", "assumptions_and_questions",
    "expected_benefit", "confidence", "limitations",
)
