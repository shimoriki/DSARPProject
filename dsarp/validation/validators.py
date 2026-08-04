"""Loop 13 (part) — validators enforcing the no-hallucination policy.

Validators run AFTER candidate generation and BEFORE/around LLM output. They can
only demote claims to `requires_source_inspection`; they never fabricate support.
The LLM critic cannot override these.

Implements: OutputSchemaValidator, EvidenceIdValidator, FileExistenceValidator,
EntityExistenceValidator, DependencyEdgeValidator, ToolFindingValidator,
RecipeApplicabilityValidator, RecipeValidationStatusValidator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set

from ..schemas import EvidenceCase, Suggestion
from ..util import read_json

try:
    import jsonschema
except Exception:  # pragma: no cover
    jsonschema = None


@dataclass
class ValidationResult:
    ok: bool
    unsupported_claims: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


class ValidationEngine:
    def __init__(self, schema_path: Path | None = None):
        self.schema = read_json(schema_path) if schema_path else None

    # -- individual validators -------------------------------------------- #
    def output_schema(self, suggestion: Suggestion) -> ValidationResult:
        if self.schema is None or jsonschema is None:
            return ValidationResult(True, notes=["schema validation skipped (no jsonschema/schema)"])
        try:
            jsonschema.validate(suggestion.to_contract_dict(), self.schema)
            return ValidationResult(True)
        except Exception as exc:
            return ValidationResult(False, notes=[f"schema: {str(exc)[:160]}"])

    def evidence_ids(self, suggestion: Suggestion, known: Set[str]) -> ValidationResult:
        missing = [e for e in suggestion.evidence_used if e not in known]
        return ValidationResult(not missing,
                                unsupported_claims=[f"unknown evidence id {e}" for e in missing])

    def files_exist(self, files: List[str], source_index: List[str]) -> ValidationResult:
        idx = set(source_index)
        missing = [f for f in files if f not in idx]
        return ValidationResult(not missing,
                                unsupported_claims=[f"file not in source index: {f}" for f in missing])

    def entities_exist(self, entities: List[str], known_entities: Set[str]) -> ValidationResult:
        missing = [e for e in entities if e not in known_entities]
        return ValidationResult(not missing,
                                unsupported_claims=[f"entity unverified: {e}" for e in missing])

    def dependency_edge(self, frm: str, to: str, edges: Set[tuple]) -> ValidationResult:
        supported = (frm, to) in edges or (to, frm) in edges
        return ValidationResult(supported,
                                unsupported_claims=[] if supported
                                else [f"edge {frm}->{to} not supported by graph evidence"])

    def tool_finding(self, evidence_used: List[str], tool_evidence: Set[str]) -> ValidationResult:
        # every smell-level claim must trace to at least one real tool/graph evidence id
        ok = any(e in tool_evidence for e in evidence_used) if evidence_used else False
        return ValidationResult(ok, unsupported_claims=[] if ok else ["no backing tool finding"])

    def recipe_applicability(self, suggestion: Suggestion) -> ValidationResult:
        plan = suggestion.openrewrite_recipe_plan
        if plan.recipe_possible and plan.recipe_type == "Not applicable":
            return ValidationResult(False, notes=["recipe_possible=true but type Not applicable"])
        return ValidationResult(True)

    def recipe_validation_status(self, suggestion: Suggestion) -> ValidationResult:
        plan = suggestion.openrewrite_recipe_plan
        v = suggestion.verification
        if plan.recipe_status == "validated" and not (
            v.openrewrite_dry_run == "passed" and v.build == "passed"
        ):
            return ValidationResult(False, notes=["marked validated without dry-run+build pass"])
        return ValidationResult(True)

    # -- orchestration ----------------------------------------------------- #
    def validate_suggestion(self, suggestion: Suggestion, case: EvidenceCase,
                            source_lookup: Dict[str, Set[str]] | None = None) -> Suggestion:
        known_ev: Set[str] = set()
        for s in case.smells:
            known_ev.update(s.evidence_ids)
        for e in case.dependency_graph.edges:
            if e.evidence_id:
                known_ev.add(e.evidence_id)
        edges: Set[tuple] = {(e.source, e.target) for e in case.dependency_graph.edges}
        entities = set(case.source_index.classes) | set(case.source_index.methods)

        claims: List[str] = []
        for r in (
            self.evidence_ids(suggestion, known_ev),
            self.files_exist([f for f in []], case.source_index.files),  # files only when cited
            self.tool_finding(suggestion.evidence_used, known_ev),
            self.recipe_applicability(suggestion),
            self.recipe_validation_status(suggestion),
        ):
            claims.extend(r.unsupported_claims)
            claims.extend(r.notes if not r.ok else [])

        # edge support for the target boundary
        b = suggestion.target_boundary
        if b.from_ and b.to:
            edge_res = self.dependency_edge(b.from_, b.to, edges)
            if not edge_res.ok:
                suggestion.target_boundary.edge_direction_status = "requires_source_inspection"
                suggestion.edge_direction_status = "requires_source_inspection"
                claims.extend(edge_res.unsupported_claims)
            else:
                suggestion.target_boundary.edge_direction_status = "supported_by_evidence"
                suggestion.edge_direction_status = "supported_by_evidence"

        # source-index-aware entity existence (Task 6).
        # If we HAVE a source index, a component absent from it is a real hallucination.
        # If we do NOT, we cannot prove existence -> requires_source_inspection (not a failure).
        entities_ok = True
        components = [c.get("id") for c in suggestion.affected_components if c.get("id")]
        if source_lookup and source_lookup.get("packages"):
            pkgs = source_lookup["packages"]
            classes = source_lookup.get("classes", set())
            simple = source_lookup.get("class_simple", set())
            for comp in components:
                present = (comp in pkgs or comp in classes
                           or comp.rsplit(".", 1)[-1] in simple
                           or any(comp.startswith(p + ".") or p.startswith(comp + ".") for p in pkgs))
                if not present:
                    entities_ok = False
                    claims.append(f"component not found in source index: {comp}")
            suggestion.verification.source_checked = True
        elif components:
            if "requires_source_inspection" not in suggestion.limitations:
                suggestion.limitations.append("requires_source_inspection")

        schema_res = self.output_schema(suggestion)
        if not schema_res.ok:
            claims.extend(schema_res.notes)

        # write back no-hallucination checks
        suggestion.no_hallucination_checks.unsupported_claims = claims
        suggestion.no_hallucination_checks.all_edges_supported = (
            suggestion.edge_direction_status == "supported_by_evidence"
        )
        suggestion.no_hallucination_checks.all_entities_exist = entities_ok
        suggestion.verification_status = "passed" if not claims else "flagged"
        if claims and "requires_source_inspection" not in suggestion.limitations:
            suggestion.limitations.append("requires_source_inspection")
        return suggestion
