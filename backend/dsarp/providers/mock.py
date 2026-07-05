"""Deterministic offline provider for tests and the no-model demo.

Recognizes the prompt markers used by dsarp.agents.prompts and returns a
schema-valid response built only from facts inside the prompt, so the whole
pipeline (including grounding checks) can be exercised without any model
server. It is intentionally boring and honest: unknown directions are marked
'requires_source_inspection'.
"""
from __future__ import annotations

import json
import re
import time

from ..config import ModelConfig
from .base import ChatResult, estimate_tokens

_CASE_RE = re.compile(r"BEGIN_CASE_JSON\s*(\{.*?\})\s*END_CASE_JSON", re.DOTALL)
_SKILLOPT_RE = re.compile(r"BEGIN_CURRENT_SKILL\s*(.*?)\s*END_CURRENT_SKILL", re.DOTALL)


class MockProvider:
    name = "mock"

    def __init__(self, cfg: ModelConfig):
        self.cfg = cfg
        self.model_id = cfg.model_id or "mock"

    def chat(self, system: str, user: str, *, temperature: float | None = None,
             max_tokens: int | None = None) -> ChatResult:
        start = time.perf_counter()
        if "BEGIN_CRITIC_TASK" in user:
            text = self._critic_response()
        elif "BEGIN_SKILLOPT_TASK" in user:
            text = self._skillopt_response(user)
        else:
            text = self._suggestion_response(user)
        elapsed = time.perf_counter() - start
        pt, ct = estimate_tokens(system + user), estimate_tokens(text)
        return ChatResult(text=text, prompt_tokens=pt, completion_tokens=ct,
                          total_tokens=pt + ct,
                          runtime_seconds=round(elapsed + 0.01, 3))

    def _suggestion_response(self, user: str) -> str:
        m = _CASE_RE.search(user)
        case = json.loads(m.group(1)) if m else {}
        components = case.get("affected_components", [])[:4]
        deps = case.get("dependency_evidence", [])
        finding_ids = [f.get("evidence_id") for f in case.get("tool_findings", [])]
        edge_ids = [d.get("evidence_id") for d in deps]
        observed = [
            f"{d.get('from')} depends on {d.get('to')} ({d.get('evidence_id')})"
            for d in deps[:5]
        ]
        for f in case.get("tool_findings", [])[:3]:
            sev = f.get("attributes", {}).get("severity")
            if sev:
                observed.append(
                    f"{f.get('tool')} reports severity '{sev}' ({f.get('evidence_id')})")
        if not observed:
            observed = ["Tool reported the smell; no edge-level facts available. "
                        "Requires source inspection."]
        boundary_pair = components[:2] if len(components) >= 2 else components
        supported = False
        if len(boundary_pair) == 2:
            supported = any(
                (d.get("from"), d.get("to")) in
                [(boundary_pair[0], boundary_pair[1]), (boundary_pair[1], boundary_pair[0])]
                for d in deps)
        suggestion = {
            "evidence_used": [i for i in finding_ids + edge_ids if i],
            "observed_tool_evidence": observed,
            "candidate_boundary_to_inspect": {
                "components": boundary_pair,
                "edge_direction_status": (
                    "supported_by_evidence" if supported else "requires_source_inspection"),
                "reason": ("Dependency evidence covers this pair."
                           if supported else
                           "No imported edge covers this pair. Requires source inspection."),
            },
            "recommended_refactoring": "Dependency Inversion",
            "rationale": (
                "The tools report a cyclic dependency among "
                + ", ".join(components)
                + ". Introducing an abstraction owned by the more stable component "
                  "removes one direction of the cycle with a minimal, local change."),
            "implementation_steps": [
                f"Define an interface in {boundary_pair[0]} capturing the operations "
                f"currently pulled from {boundary_pair[-1]}." if boundary_pair else
                "Define an interface capturing the cross-boundary operations.",
                f"Implement the interface in {boundary_pair[-1]} and register the "
                "implementation at composition time." if boundary_pair else
                "Implement the interface on the providing side.",
                "Replace the direct import with the interface and re-run the "
                "dependency analysis to confirm the cycle is gone.",
            ],
            "affected_components": components,
            "risks_and_tradeoffs": [
                "Added indirection: one more type to navigate when reading the code.",
                "If the interface is cut too wide, the cycle can reappear later.",
            ],
            "assumptions_and_questions": [
                "Which concrete classes participate in the cycle? Requires source inspection.",
            ],
            "expected_benefit": "Cycle removed; components become independently buildable and testable.",
            "confidence": 0.55 if not supported else 0.7,
            "limitations": ("Edge directions not fully covered by evidence; boundary "
                            "must be confirmed by source inspection."
                            if not supported else
                            "Based on tool evidence only; no code was compiled or tested."),
        }
        return json.dumps(suggestion, indent=2)

    def _critic_response(self) -> str:
        scores = {c: {"score": 3, "reason": "Mock critic default; verify manually."}
                  for c in ("evidence_grounding", "refactoring_relevance",
                            "architectural_reasoning", "minimality_and_safety",
                            "actionability", "human_confidence", "cost_efficiency")}
        return json.dumps(scores, indent=2)

    def _skillopt_response(self, user: str) -> str:
        m = _SKILLOPT_RE.search(user)
        current = m.group(1) if m else "# Skill"
        revised = current.rstrip() + (
            "\n\n## Revision notes (mock optimizer)\n"
            "- Always cite at least one evidence_id per observed fact.\n"
            "- Provide at least three implementation steps naming the touched components.\n"
            "- State at least two risks and one open question when direction evidence is missing.\n")
        return revised
