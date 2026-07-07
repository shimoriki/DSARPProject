"""Held-out validation of skill versions and the gated promotion rule.

Both skill versions run on the same validation-split cases with the same
model. Per-run scores use human HGRS when a review exists, otherwise a
clearly-labeled deterministic proxy (weighted suggested scores). Promotion
requires: mean held-out HGRS improvement >= threshold, no drop in evidence
grounding, zero critical hallucinations for the candidate, and a recorded
human approval. The production skill file is never overwritten.
"""
from __future__ import annotations

import json

from ..config import AppConfig
from ..hgrs import compute_hgrs
from ..log import get_logger
from ..models.suggestion import AgentMode
from ..providers.base import ModelProvider
from ..agents.runner import run_suggestion
from ..store.repos import Store

log = get_logger("validate")


def _score_run(store: Store, cfg: AppConfig, run: dict) -> dict | None:
    """Human HGRS when reviewed; deterministic proxy otherwise."""
    if run["status"] != "ok":
        # a failed run is scored at the rubric floor, not excluded — skills and
        # models must not look better by producing invalid output
        return {"hgrs": 1.0, "grounding": 1, "source": "failed_run_floor",
                "critical_hallucination": False, "run_failed": True}
    review = store.review_for_run(run["run_id"])
    checks = json.loads(run.get("structural_checks_json") or "{}")
    critical = bool(checks.get("critical_hallucination"))
    if review:
        return {"hgrs": review["hgrs"], "grounding": review["evidence_grounding"],
                "source": "human_review", "critical_hallucination": critical,
                "run_failed": False}
    suggested = checks.get("suggested_scores") or {}
    if not suggested:
        return None
    scores = {c: v["score"] for c, v in suggested.items()}
    return {"hgrs": compute_hgrs(scores, cfg.hgrs_weights),
            "grounding": scores.get("evidence_grounding"),
            "source": "deterministic_proxy", "critical_hallucination": critical,
            "run_failed": False}


def _evaluate_version(cfg: AppConfig, store: Store, provider: ModelProvider,
                      skill_name: str, version: str, cases: list) -> dict:
    skill_row = store.get_skill(skill_name, version)
    if not skill_row:
        raise ValueError(f"skill {skill_name} {version} is not registered")
    skill_text = cfg.resolve(skill_row["file_path"]).read_text(encoding="utf-8")

    per_run = []
    for case in cases:
        run = run_suggestion(cfg, store, provider, case, AgentMode.tool_evidence,
                             skill_name=skill_name, skill_version=version,
                             skill_text=skill_text)
        scored = _score_run(store, cfg, run)
        if scored is not None:
            scored["run_id"] = run["run_id"]
            scored["case_id"] = case.case_id
            per_run.append(scored)

    valid = [r for r in per_run if r["hgrs"] is not None]
    n = len(valid)
    return {
        "version": version,
        "runs": per_run,
        "n_scored": n,
        "n_failed": sum(1 for r in per_run if r.get("run_failed")),
        "mean_hgrs": round(sum(r["hgrs"] for r in valid) / n, 3) if n else None,
        "mean_grounding": round(sum(r["grounding"] for r in valid) / n, 3) if n else None,
        "critical_hallucinations": sum(1 for r in per_run if r["critical_hallucination"]),
        "score_sources": sorted({r["source"] for r in per_run}),
    }


def validate_skills(cfg: AppConfig, store: Store, provider: ModelProvider,
                    project_name: str, skill_name: str,
                    baseline_version: str, candidate_version: str) -> dict:
    case_rows = store.list_cases(project_id=project_name, split="validation")
    if not case_rows:
        raise ValueError(
            f"project '{project_name}' has no validation-split cases; "
            "run the split first (dsarp evidence split)")
    cases = [store.get_case(r["id"]) for r in case_rows]

    log.info("validating %s: %s vs %s on %d held-out cases",
             skill_name, baseline_version, candidate_version, len(cases))
    base_eval = _evaluate_version(cfg, store, provider, skill_name, baseline_version, cases)
    cand_eval = _evaluate_version(cfg, store, provider, skill_name, candidate_version, cases)

    improvement = None
    grounding_delta = None
    if base_eval["mean_hgrs"] is not None and cand_eval["mean_hgrs"] is not None:
        improvement = round(cand_eval["mean_hgrs"] - base_eval["mean_hgrs"], 3)
    if base_eval["mean_grounding"] is not None and cand_eval["mean_grounding"] is not None:
        grounding_delta = round(cand_eval["mean_grounding"] - base_eval["mean_grounding"], 3)

    gate = cfg.promotion
    reasons = []
    if improvement is None:
        reasons.append("could not compute mean HGRS for both versions")
    elif improvement < gate.min_hgrs_improvement:
        reasons.append(f"HGRS improvement {improvement} < required {gate.min_hgrs_improvement}")
    if grounding_delta is not None and grounding_delta < -gate.max_grounding_drop:
        reasons.append(f"evidence grounding decreased by {abs(grounding_delta)}")
    if cand_eval["critical_hallucinations"] > 0:
        reasons.append(
            f"candidate produced {cand_eval['critical_hallucinations']} critical "
            "hallucination(s) (unsupported evidence IDs / components / directions)")
    passed = not reasons

    report = {
        "project": project_name,
        "skill_name": skill_name,
        "held_out_cases": [c.case_id for c in cases],
        "baseline": base_eval,
        "candidate": cand_eval,
        "hgrs_improvement": improvement,
        "grounding_delta": grounding_delta,
        "promotion_gate": {
            "min_hgrs_improvement": gate.min_hgrs_improvement,
            "max_grounding_drop": gate.max_grounding_drop,
            "no_critical_hallucination": True,
            "human_approval_required": True,
        },
        "passed": passed,
        "fail_reasons": reasons,
        "note": ("Scores marked 'deterministic_proxy' come from automatic checks and "
                 "are NOT human HGRS; review validation runs in the console for "
                 "human-grade evidence before approving."),
    }
    report_id = store.save_validation_report(
        skill_name, baseline_version, candidate_version, report, passed)
    report["report_id"] = report_id
    return report


def promote_candidate(cfg: AppConfig, store: Store, report_id: str,
                      approver: str) -> dict:
    """Promote only after gate passed AND explicit human approval."""
    row = store.get_validation_report(report_id)
    if not row:
        raise ValueError(f"unknown validation report {report_id}")
    if not row["passed"]:
        raise ValueError("validation gate did not pass; promotion refused")

    store.mark_report(report_id, human_approved=True)
    skill_name = row["skill_name"]
    candidate_version = row["candidate_version"]
    baseline_version = row["baseline_version"]

    candidate = store.get_skill(skill_name, candidate_version)
    if not candidate:
        raise ValueError(f"candidate skill {skill_name} {candidate_version} missing")

    # promoted version keeps its own file; production file is never overwritten
    promoted_version = candidate_version.replace("_candidate", "")
    store.register_skill(skill_name, promoted_version, candidate["file_path"],
                         status="production", parent_version=baseline_version,
                         notes=f"promoted from {candidate_version} via report {report_id}")
    store.set_skill_status(skill_name, candidate_version, "archived")
    store.set_skill_status(skill_name, baseline_version, "archived")
    store.mark_report(report_id, promoted=True)
    store.audit("skill", f"{skill_name}:{promoted_version}", "promoted",
                actor=approver, details={"report_id": report_id})
    log.info("promoted %s %s (approved by %s)", skill_name, promoted_version, approver)
    return {"skill_name": skill_name, "production_version": promoted_version,
            "archived": [baseline_version, candidate_version]}
