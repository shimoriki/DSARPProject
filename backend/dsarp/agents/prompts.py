"""Prompt builders for the three agent modes. PROMPT_VERSION is tracked per run."""
from __future__ import annotations

import json

from ..models.evidence import EvidenceCase
from ..models.suggestion import AgentMode

PROMPT_VERSION = "p2"

_OUTPUT_SCHEMA = """{
  "evidence_used": ["EVIDENCE_ID_1", "EVIDENCE_ID_2"],
  "observed_tool_evidence": ["org.example.a depends on org.example.b (GRAPH_EDGE_002)",
                             "arcan reports severity high (ARCAN_CD_001)"],
  "candidate_boundary_to_inspect": {
    "components": ["componentA", "componentB"],
    "edge_direction_status": "supported_by_evidence | requires_source_inspection",
    "reason": "string"
  },
  "recommended_refactoring": "Dependency Inversion",
  "rationale": "string",
  "implementation_steps": ["step 1", "step 2", "step 3"],
  "affected_components": ["componentA"],
  "risks_and_tradeoffs": ["risk 1"],
  "assumptions_and_questions": ["question 1"],
  "expected_benefit": "string",
  "confidence": 0.0,
  "limitations": "string"
}"""

_BASE_SYSTEM = """You are an architectural refactoring assistant. You receive one normalized \
architecture-smell case and must propose exactly one refactoring.

Respond with ONLY a single JSON object matching this schema (no markdown, no prose):

""" + _OUTPUT_SCHEMA + """

Rules:
- recommended_refactoring must be EXACTLY ONE of: Extract Interface,
  Dependency Inversion, Move Class, Move Method, Facade, Adapter,
  Split Component, Other. Pick a single value — never combine them.
- confidence is a number between 0.0 and 1.0.
- implementation_steps must be concrete, ordered, and name the components they touch.
- Every list field contains PLAIN STRINGS only — never nested objects. The values
  shown in the schema above are examples of the expected style, not fixed text."""

_EVIDENCE_RULES = """
STRICT EVIDENCE RULES (violations make the answer unusable):
1. Only reference evidence IDs that literally appear in the case JSON.
2. Never claim an exact class, method, dependency edge, or dependency direction
   unless that exact fact appears in the case's dependency_evidence or tool_findings.
3. Every entry in observed_tool_evidence must cite the evidence_id it comes from.
4. If a needed direction or detail is not in the evidence, set
   edge_direction_status to "requires_source_inspection" and write
   "Requires source inspection." in the relevant field.
5. affected_components may only contain components listed in the case.
6. Read the case's "limitations" list and respect it."""


def system_prompt(mode: AgentMode, skill_text: str | None) -> str:
    if mode == AgentMode.baseline:
        return _BASE_SYSTEM
    parts = [_BASE_SYSTEM]
    if skill_text:
        parts.append("\nApply the following reusable refactoring skill:\n"
                     "--- SKILL DOCUMENT ---\n" + skill_text + "\n--- END SKILL ---")
    if mode == AgentMode.tool_evidence:
        parts.append(_EVIDENCE_RULES)
    return "\n".join(parts)


def user_prompt(case: EvidenceCase) -> str:
    case_json = json.dumps(case.public_dict(), indent=2)
    return (
        f"Architecture smell case for project '{case.project_id}' "
        f"(architecture: {case.architecture_type}, component type: {case.component_type.value}).\n"
        "BEGIN_CASE_JSON\n" + case_json + "\nEND_CASE_JSON\n"
        "Produce the JSON suggestion now.")


def repair_prompt(previous_output: str, validation_error: str) -> str:
    return (
        "Your previous response was not valid against the required JSON schema.\n"
        f"Validation error:\n{validation_error}\n\n"
        "Previous response:\n" + previous_output[:4000] + "\n\n"
        "Return ONLY the corrected JSON object. Do not invent new facts; if a value "
        "is unknown, use \"Requires source inspection.\" or an empty list.")
