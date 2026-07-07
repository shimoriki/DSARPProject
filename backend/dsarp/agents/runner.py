"""Agent runner: builds prompts, calls the local model, validates strictly.

Exactly one repair attempt is allowed for invalid JSON. Malformed responses
are stored verbatim in malformed_outputs — never silently patched. Fields the
model does not own (run_id, project_id, ...) are stamped from run metadata.
"""
from __future__ import annotations

import json
import uuid

from pydantic import ValidationError

from ..config import AppConfig
from ..log import get_logger
from ..models.evidence import EvidenceCase
from ..models.suggestion import (MODEL_OWNED_FIELDS, AgentMode,
                                 RefactoringSuggestion)
from ..normalize import EVIDENCE_VERSION
from ..providers.base import ModelProvider, ProviderError
from ..store.repos import Store
from .. import checks as checks_mod
from . import prompts

log = get_logger("runner")


class AgentRunError(RuntimeError):
    pass


def extract_json(text: str) -> str:
    """Return the first balanced top-level JSON object in text."""
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found in model output")
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise ValueError("unbalanced JSON object in model output")


_STRING_LIST_FIELDS = ("evidence_used", "observed_tool_evidence",
                       "implementation_steps", "affected_components",
                       "risks_and_tradeoffs", "assumptions_and_questions")


def _flatten_string_lists(payload: dict) -> dict:
    """Mechanical format repair for list-of-string fields.

    Small local models sometimes wrap list items in objects (e.g.
    {"fact": "..."}). Flattening an item to its string value(s) changes format
    only, never content — the raw response is stored verbatim regardless.
    """
    for field in _STRING_LIST_FIELDS:
        value = payload.get(field)
        if not isinstance(value, list):
            continue
        flat: list[str] = []
        for item in value:
            if isinstance(item, str):
                flat.append(item)
            elif isinstance(item, dict):
                strings = [v for v in item.values() if isinstance(v, str) and v.strip()]
                flat.append(" — ".join(strings) if strings
                            else json.dumps(item, ensure_ascii=False))
            else:
                flat.append(json.dumps(item, ensure_ascii=False))
        payload[field] = flat
    # a model that lists several options ("A | B") gets its first choice —
    # format repair of an ambiguous answer, recorded verbatim in raw_response
    rec = payload.get("recommended_refactoring")
    if isinstance(rec, str) and "|" in rec:
        payload["recommended_refactoring"] = rec.split("|")[0].strip()
    return payload


def _validate(model_text: str, run_meta: dict) -> RefactoringSuggestion:
    payload = json.loads(extract_json(model_text))
    if not isinstance(payload, dict):
        raise ValueError("model output is not a JSON object")
    payload = _flatten_string_lists(payload)
    owned = {k: payload[k] for k in MODEL_OWNED_FIELDS if k in payload}
    merged = {**owned, **run_meta}
    return RefactoringSuggestion.model_validate(merged)


def run_suggestion(cfg: AppConfig, store: Store, provider: ModelProvider,
                   case: EvidenceCase, mode: AgentMode,
                   skill_name: str | None = None, skill_version: str | None = None,
                   skill_text: str | None = None,
                   experiment_id: str | None = None) -> dict:
    """Run one agent on one evidence case; persist and return the run row."""
    run_id = str(uuid.uuid4())
    run_meta = {
        "run_id": run_id,
        "project_id": case.project_id,
        "smell_id": case.smell_id,
        "smell_type": case.smell_type,
        "agent_mode": mode.value,
        "model_id": provider.model_id,
        "skill_version": skill_version or "none",
    }
    system = prompts.system_prompt(mode, skill_text if mode != AgentMode.baseline else None)
    user = prompts.user_prompt(case)

    record: dict = {
        "run_id": run_id, "project_id": case.project_id, "case_id": case.case_id,
        "smell_id": case.smell_id, "agent_mode": mode.value,
        "provider": provider.name, "model_id": provider.model_id,
        "skill_name": skill_name if mode != AgentMode.baseline else None,
        "skill_version": (skill_version or "none") if mode != AgentMode.baseline else "none",
        "prompt_version": prompts.PROMPT_VERSION,
        "evidence_version": EVIDENCE_VERSION,
        "experiment_id": experiment_id,
        "repair_attempted": 0,
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
        "runtime_seconds": 0.0,
    }

    def _accumulate(result) -> None:
        record["prompt_tokens"] += result.prompt_tokens or 0
        record["completion_tokens"] += result.completion_tokens or 0
        record["total_tokens"] += result.total_tokens or 0
        record["runtime_seconds"] = round(
            record["runtime_seconds"] + (result.runtime_seconds or 0.0), 3)

    try:
        result = provider.chat(system, user)
    except ProviderError as exc:
        record.update(status="error", error=str(exc), raw_response=None)
        store.save_agent_run(record)
        log.error("provider error on case %s: %s", case.smell_id, exc)
        return store.get_run(run_id)

    _accumulate(result)
    record["raw_response"] = result.text
    suggestion = None
    first_error = ""
    try:
        suggestion = _validate(result.text, run_meta)
    except (ValueError, ValidationError, json.JSONDecodeError) as exc:
        first_error = str(exc)
        # single repair attempt, then give up honestly
        record["repair_attempted"] = 1
        try:
            repair = provider.chat(system, prompts.repair_prompt(result.text, first_error))
            _accumulate(repair)
            record["raw_response"] = repair.text
            suggestion = _validate(repair.text, run_meta)
        except (ValueError, ValidationError, json.JSONDecodeError, ProviderError) as exc2:
            store.save_malformed(run_id, record.get("raw_response") or "",
                                 f"first: {first_error} | repair: {exc2}")
            record.update(status="invalid_json",
                          error=f"invalid JSON after repair attempt: {exc2}")
            store.save_agent_run(record)
            log.warning("invalid JSON for case %s after repair", case.smell_id)
            return store.get_run(run_id)

    record["status"] = "ok"
    record["suggestion_json"] = json.dumps(suggestion.model_dump(mode="json"), indent=2)

    structural = checks_mod.run_structural_checks(suggestion, case, record, store)
    record["structural_checks_json"] = json.dumps(structural, default=str)
    store.save_agent_run(record)
    store.save_suggested_scores(run_id, "deterministic", structural["suggested_scores"])
    return store.get_run(run_id)
