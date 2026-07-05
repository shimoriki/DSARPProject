"""Normalized evidence model shared by all tool adapters."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class ComponentType(str, Enum):
    package = "package"
    module = "module"
    class_ = "class"
    service = "service"
    bounded_context = "bounded_context"
    deployment_unit = "deployment_unit"


class ToolFinding(BaseModel):
    tool: str
    tool_record_id: str
    evidence_id: str
    raw_source_file: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)


class DependencyEvidence(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_component: str = Field(alias="from")
    to_component: str = Field(alias="to")
    relation_type: str = "depends_on"
    evidence_id: str
    confidence: float = 1.0
    source: str = "static_graph"


class MetricEvidence(BaseModel):
    evidence_id: str
    component: str = ""
    name: str
    value: Union[float, int, str]
    tool: str = ""


class EvidenceCase(BaseModel):
    """One normalized smell case with full provenance.

    The agent may only assert facts that appear here (or that were read from
    local source when source inspection is explicitly enabled). Anything else
    must be marked "Requires source inspection."
    """
    model_config = ConfigDict(populate_by_name=True)

    case_id: str
    project_id: str
    source_revision: Optional[str] = None
    architecture_type: str = "package-based-java"
    component_type: ComponentType = ComponentType.package
    smell_id: str
    smell_type: str
    smell_key: str = "custom_tool_smell"
    affected_components: list[str] = Field(default_factory=list)
    tool_findings: list[ToolFinding] = Field(default_factory=list)
    dependency_evidence: list[DependencyEvidence] = Field(default_factory=list)
    metrics: list[MetricEvidence] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    def all_evidence_ids(self) -> set[str]:
        ids = {f.evidence_id for f in self.tool_findings}
        ids |= {d.evidence_id for d in self.dependency_evidence}
        ids |= {m.evidence_id for m in self.metrics}
        return ids

    def edge_pairs(self) -> set[tuple[str, str]]:
        return {(d.from_component, d.to_component) for d in self.dependency_evidence}

    def public_dict(self) -> dict[str, Any]:
        """Serialization with `from`/`to` aliases, as shown to agents and UI."""
        return self.model_dump(by_alias=True, mode="json")
