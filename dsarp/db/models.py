"""Row helpers — thin mappers between domain objects and DB rows.

Kept as plain functions returning (columns, values) tuples so the Store can
UPSERT uniformly. Complex objects go to the JSON `payload` column.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Tuple


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(obj: Any) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


def repository_row(project_id: str, repo_url: str = "", local_path: str = "",
                   split: str = "", revision: str = "", commit_count: int = 0,
                   payload: Dict | None = None) -> Tuple[str, Dict[str, Any]]:
    return "repositories", {
        "project_id": project_id, "repo_url": repo_url, "local_path": local_path,
        "split": split, "revision": revision, "commit_count": commit_count,
        "updated_at": now_iso(), "payload": _json(payload or {}),
    }


def tool_run_row(project_id: str, tool: str, mode: str, status: str,
                 finding_count: int = 0, command: str = "", version: str = "",
                 revision: str = "", output_path: str = "", log_path: str = "",
                 payload: Dict | None = None) -> Tuple[str, Dict[str, Any]]:
    return "tool_runs", {
        "project_id": project_id, "tool": tool, "mode": mode, "status": status,
        "command": command, "version": version, "revision": revision,
        "finding_count": finding_count, "output_path": output_path,
        "log_path": log_path, "created_at": now_iso(), "payload": _json(payload or {}),
    }


def suggestion_row(s: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    plan = s.get("openrewrite_recipe_plan", {})
    return "suggestions", {
        "suggestion_id": s["suggestion_id"], "case_id": s.get("case_id"),
        "project_id": s.get("project_id"), "revision": s.get("revision"),
        "rank": s.get("rank"), "score": s.get("score"), "confidence": s.get("confidence"),
        "smell_type": s.get("smell_type"), "refactoring_type": s.get("refactoring_type"),
        "verification_status": s.get("verification_status"),
        "recipe_status": plan.get("recipe_status"),
        "created_at": now_iso(), "payload": _json(s),
    }


def hgrs_row(r: Dict[str, Any], project_id: str = "") -> Tuple[str, Dict[str, Any]]:
    return "hgrs_reviews", {
        "review_id": r["review_id"], "suggestion_id": r.get("suggestion_id"),
        "project_id": project_id, "reviewer": r.get("reviewer"),
        "weighted_score": r.get("weighted_score"),
        "would_try_it": int(bool(r.get("would_try_it"))),
        "preferred": int(bool(r.get("preferred"))),
        "created_at": now_iso(), "payload": _json(r),
    }


def token_report_row(rep: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    return "token_reports", {
        "run_id": rep.get("run_id"), "project_id": rep.get("project_id"),
        "total_model_calls": rep.get("total_model_calls"),
        "cache_hits": rep.get("cache_hits"),
        "estimated_tokens_saved": rep.get("estimated_tokens_saved"),
        "created_at": now_iso(), "payload": _json(rep),
    }


def model_run_row(kind: str, name: str, version: str = "",
                  metrics: Dict | None = None) -> Tuple[str, Dict[str, Any]]:
    return "model_runs", {
        "kind": kind, "name": name, "version": version,
        "metrics": _json(metrics or {}), "created_at": now_iso(),
        "payload": _json({}),
    }
