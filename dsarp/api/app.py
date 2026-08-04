"""Task 16 — FastAPI backend so other agents can consume DSARP.

All outputs are the same schema-valid objects the CLI/UI use. Reads from files
(source of truth) with optional DB. FastAPI is an optional dependency: create_app
raises a clear error if it is not installed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import load_config
from ..schemas import EvidenceCase, HGRSReview
from ..util import read_json, read_jsonl, append_jsonl


def create_app(profile: str = "local"):
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "FastAPI not installed. `pip install fastapi uvicorn` to use the backend.") from exc

    cfg = load_config(profile)
    app = FastAPI(title="DSARP Evidence-Based Refactoring Agent API", version="0.1.0")

    def _outputs(pid: str) -> Path:
        return cfg.data_dir / "outputs" / pid

    class RunRequest(BaseModel):
        project_id: str
        top_k: int = 3
        model: Optional[str] = None

    class ReviewRequest(BaseModel):
        suggestion_id: str
        project_id: str = ""
        reviewer: str = "api"
        scores: Dict[str, float] = {}
        would_try_it: bool = False
        preferred: bool = False
        notes: str = ""

    @app.get("/projects")
    def projects() -> List[Dict[str, Any]]:
        norm = cfg.data_dir / "normalized"
        out = []
        for f in (norm.glob("*.json") if norm.exists() else []):
            case = read_json(f) or {}
            out.append({"project_id": case.get("project_id", f.stem),
                        "revision": case.get("revision"), "smells": len(case.get("smells", []))})
        return out

    @app.get("/tool-runs")
    def tool_runs(project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            from ..db import Store
            return Store(cfg.db_path).list_tool_runs(project_id)
        except Exception:
            return []

    @app.get("/evidence-cases")
    def evidence_cases() -> List[Dict[str, Any]]:
        norm = cfg.data_dir / "normalized"
        return [read_json(f) for f in (norm.glob("*.json") if norm.exists() else [])]

    @app.get("/suggestions")
    def suggestions(project_id: str) -> List[Dict[str, Any]]:
        return read_json(_outputs(project_id) / "suggestions.json", default=[]) or []

    @app.get("/suggestions/{suggestion_id}")
    def suggestion(suggestion_id: str, project_id: str) -> Dict[str, Any]:
        for s in read_json(_outputs(project_id) / "suggestions.json", default=[]) or []:
            if s.get("suggestion_id") == suggestion_id:
                return s
        raise HTTPException(status_code=404, detail="suggestion not found")

    @app.post("/suggestions/run")
    def run_suggestions(req: RunRequest) -> Dict[str, Any]:
        from ..pipeline import InferencePipeline
        from ..models.manager import resolve_override
        from ..export.report import build_report, write_report, write_suggestions
        data = read_json(cfg.data_dir / "normalized" / f"{req.project_id}.json")
        if not data:
            raise HTTPException(status_code=404, detail="no normalized evidence; prepare first")
        case = EvidenceCase(**data)
        override = resolve_override(cfg, req.model)
        pipe = InferencePipeline(cfg, req.top_k, model_override=override)
        sugs, report = pipe.run(case)
        write_suggestions(_outputs(req.project_id) / "suggestions.json", sugs)
        write_report(_outputs(req.project_id) / "report.json",
                     build_report(case.project_id, case.revision, sugs, report))
        return {"project_id": req.project_id, "suggestions": len(sugs),
                "grounding": report}

    @app.post("/reviews")
    def add_review(req: ReviewRequest) -> Dict[str, Any]:
        review = HGRSReview(suggestion_id=req.suggestion_id, reviewer=req.reviewer,
                            scores=req.scores, would_try_it=req.would_try_it,
                            preferred=req.preferred, notes=req.notes).recompute()
        append_jsonl(_outputs(req.project_id or "unknown") / "hgrs_reviews.jsonl",
                     review.model_dump())
        return {"review_id": review.review_id, "weighted_score": review.weighted_score}

    @app.get("/reports/token")
    def token_report(project_id: str) -> Dict[str, Any]:
        rep = read_json(_outputs(project_id) / "report.json", default={}) or {}
        return rep.get("token_optimisation", {})

    @app.get("/reports/cassandra")
    def cassandra_report() -> Dict[str, Any]:
        return read_json(_outputs("apache-cassandra") / "report.json", default={}) or {}

    @app.get("/recipes")
    def recipes(project_id: str) -> List[Dict[str, Any]]:
        sugs = read_json(_outputs(project_id) / "suggestions.json", default=[]) or []
        return [{"suggestion_id": s["suggestion_id"], **s.get("openrewrite_recipe_plan", {})}
                for s in sugs]

    @app.post("/recipes/validate")
    def validate_recipes(project_id: str) -> Dict[str, Any]:
        from ..openrewrite.validator import RecipeValidator
        from ..repositories.manager import RepositoryManager
        repo_path = RepositoryManager(cfg.data_dir).path_for(project_id)
        rv = RecipeValidator(repo_path, cfg.data_dir / "outputs" / "recipe_logs")
        return rv.validate_file(_outputs(project_id) / "suggestions.json")

    return app
