"""FastAPI backend. Run with:  uvicorn dsarp.api:app --port 8600"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import services
from .log import get_logger

log = get_logger("api")

app = FastAPI(title="DSARP Refactoring Suggestion Studio", version="0.1.0")
_ctx: Optional[services.AppContext] = None


def ctx() -> services.AppContext:
    global _ctx
    if _ctx is None:
        _ctx = services.init_context()
    return _ctx


def _fail(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


class ProjectIn(BaseModel):
    name: str
    path: str = ""
    architecture_type: str = "package-based-java"
    component_type: str = "package"
    source_revision: Optional[str] = None


class ImportIn(BaseModel):
    tool: str
    path: str


class AnalyzeIn(BaseModel):
    tools: list[str]


class SuggestIn(BaseModel):
    project: str
    agent_mode: str = "tool_evidence"
    case_ids: Optional[list[str]] = None
    provider: Optional[str] = None
    model_id: Optional[str] = None
    skill_name: Optional[str] = None
    skill_version: Optional[str] = None
    split: Optional[str] = None
    with_critic: Optional[bool] = None


class ReviewIn(BaseModel):
    run_id: str
    scores: dict[str, int]
    would_try_it: str = "maybe"
    decision: str = "revise"
    reviewer_notes: str = ""
    edited_output_json: Optional[str] = None
    reviewer_id: Optional[str] = None


class OptimizeIn(BaseModel):
    skill_version: str
    provider: Optional[str] = None
    model_id: Optional[str] = None


class ValidateIn(BaseModel):
    project: str
    baseline_version: str
    candidate_version: str
    provider: Optional[str] = None
    model_id: Optional[str] = None


class ExportIn(BaseModel):
    min_hgrs: float = 4.0
    project: Optional[str] = None
    formats: list[str] = Field(default_factory=lambda: ["instruction", "chat", "csv"])
    lora_prep: bool = False


@app.get("/health")
def health():
    return {"status": "ok", "model_provider": ctx().cfg.model.provider,
            "model_id": ctx().cfg.model.model_id}


@app.get("/projects")
def list_projects():
    return ctx().store.list_projects()


@app.post("/projects")
def add_project(body: ProjectIn):
    return services.add_project(ctx(), body.name, body.path, body.architecture_type,
                                body.component_type, body.source_revision)


@app.post("/projects/{name}/import")
def import_file(name: str, body: ImportIn):
    try:
        return services.import_tool_file(ctx(), name, body.tool, body.path)
    except Exception as exc:
        raise _fail(exc)


@app.post("/projects/{name}/analyze")
def analyze(name: str, body: AnalyzeIn):
    try:
        return services.analyze_project(ctx(), name, body.tools)
    except Exception as exc:
        raise _fail(exc)


@app.post("/projects/{name}/evidence/build")
def build_evidence(name: str):
    try:
        return {"cases": services.rebuild_evidence(ctx(), name)}
    except Exception as exc:
        raise _fail(exc)


@app.post("/projects/{name}/evidence/split")
def split_evidence(name: str):
    try:
        return services.split_evidence(ctx(), name)
    except Exception as exc:
        raise _fail(exc)


@app.get("/projects/{name}/cases")
def list_cases(name: str, split: Optional[str] = None):
    return ctx().store.list_cases(project_id=name, split=split)


@app.get("/cases/{case_id}")
def get_case(case_id: str):
    case = ctx().store.get_case(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    return case.public_dict()


@app.post("/suggest")
def suggest(body: SuggestIn):
    try:
        return services.run_agents(
            ctx(), body.project, body.agent_mode, body.case_ids, body.provider,
            body.model_id, body.skill_name, body.skill_version, body.split,
            body.with_critic)
    except Exception as exc:
        raise _fail(exc)


@app.get("/runs")
def list_runs(project: Optional[str] = None, agent_mode: Optional[str] = None,
              status: Optional[str] = None):
    return ctx().store.list_runs(project_id=project, agent_mode=agent_mode,
                                 status=status)


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    run = ctx().store.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return run


@app.get("/runs/{run_id}/suggested-scores")
def suggested_scores(run_id: str):
    return ctx().store.get_suggested_scores(run_id)


@app.post("/reviews")
def save_review(body: ReviewIn):
    try:
        review = services.save_review(
            ctx(), body.run_id, body.scores, body.would_try_it, body.decision,
            body.reviewer_notes, body.edited_output_json, body.reviewer_id)
        return review.model_dump(mode="json")
    except Exception as exc:
        raise _fail(exc)


@app.get("/reviews")
def list_reviews(project: Optional[str] = None):
    return ctx().store.list_reviews(project_id=project)


@app.get("/skills")
def list_skills():
    return ctx().store.list_skills()


@app.post("/skills/{name}/optimize")
def optimize_skill(name: str, body: OptimizeIn):
    try:
        return services.optimize(ctx(), name, body.skill_version,
                                 body.provider, body.model_id)
    except Exception as exc:
        raise _fail(exc)


@app.post("/skills/{name}/validate")
def validate_skill(name: str, body: ValidateIn):
    try:
        return services.validate(ctx(), body.project, name, body.baseline_version,
                                 body.candidate_version, body.provider, body.model_id)
    except Exception as exc:
        raise _fail(exc)


@app.get("/validation-reports")
def validation_reports(skill: Optional[str] = None):
    rows = ctx().store.list_validation_reports(skill)
    for r in rows:
        r["report_json"] = json.loads(r["report_json"])
    return rows


@app.post("/validation/{report_id}/approve")
def approve(report_id: str, approver: Optional[str] = None):
    try:
        return services.approve_and_promote(ctx(), report_id, approver)
    except Exception as exc:
        raise _fail(exc)


@app.get("/experiments/compare")
def compare(project: Optional[str] = None, experiment_id: Optional[str] = None):
    return services.comparison_table(ctx(), project, experiment_id)


@app.post("/export/dataset")
def export_dataset(body: ExportIn):
    try:
        return services.export_dataset(ctx(), body.min_hgrs, body.project,
                                       body.formats, body.lora_prep)
    except Exception as exc:
        raise _fail(exc)
