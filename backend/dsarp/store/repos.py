"""Typed repository layer over SQLite. All persistence goes through Store."""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from ..models.evidence import EvidenceCase
from ..models.review import HumanReview
from .db import Database, utcnow


def _uid() -> str:
    return str(uuid.uuid4())


def _row_dict(row) -> dict[str, Any]:
    return dict(row) if row is not None else None


class Store:
    def __init__(self, db: Database):
        self.db = db

    # ---------------- audit ----------------
    def audit(self, entity_type: str, entity_id: str, action: str,
              actor: str = "system", details: dict | None = None) -> None:
        self.db.execute(
            "INSERT INTO audit_log(entity_type, entity_id, action, actor, details_json, at)"
            " VALUES (?,?,?,?,?,?)",
            (entity_type, entity_id, action, actor,
             json.dumps(details or {}, default=str), utcnow()),
        )

    def list_audit(self, limit: int = 200) -> list[dict]:
        rows = self.db.query(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    # ---------------- projects ----------------
    def add_project(self, name: str, path: str = "", architecture_type: str = "package-based-java",
                    component_type: str = "package", source_revision: str | None = None) -> dict:
        existing = self.get_project(name)
        if existing:
            return existing
        pid = _uid()
        self.db.execute(
            "INSERT INTO projects(id, name, path, architecture_type, component_type,"
            " source_revision, created_at) VALUES (?,?,?,?,?,?,?)",
            (pid, name, path, architecture_type, component_type, source_revision, utcnow()),
        )
        self.audit("project", pid, "created", details={"name": name})
        return self.get_project(name)

    def get_project(self, name_or_id: str) -> Optional[dict]:
        row = self.db.query_one(
            "SELECT * FROM projects WHERE name = ? OR id = ?", (name_or_id, name_or_id))
        return _row_dict(row)

    def list_projects(self) -> list[dict]:
        return [dict(r) for r in self.db.query("SELECT * FROM projects ORDER BY created_at")]

    # ---------------- tool runs / raw findings ----------------
    def create_tool_run(self, project_id: str, tool: str, mode: str,
                        source_path: str = "", command: str = "",
                        source_hash: str = "", meta: dict | None = None) -> str:
        rid = _uid()
        self.db.execute(
            "INSERT INTO tool_runs(id, project_id, tool, mode, source_path, command,"
            " source_hash, status, started_at, meta_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rid, project_id, tool, mode, source_path, command, source_hash,
             "running", utcnow(), json.dumps(meta or {})),
        )
        return rid

    def finish_tool_run(self, run_id: str, status: str, error: str = "") -> None:
        self.db.execute(
            "UPDATE tool_runs SET status = ?, error = ?, finished_at = ? WHERE id = ?",
            (status, error, utcnow(), run_id),
        )

    def list_tool_runs(self, project_id: str | None = None) -> list[dict]:
        if project_id:
            rows = self.db.query(
                "SELECT * FROM tool_runs WHERE project_id = ? ORDER BY started_at DESC",
                (project_id,))
        else:
            rows = self.db.query("SELECT * FROM tool_runs ORDER BY started_at DESC")
        return [dict(r) for r in rows]

    def add_raw_findings(self, tool_run_id: str, tool: str, records: list[dict]) -> int:
        rows = [
            (_uid(), tool_run_id, tool, rec.get("kind", "smell"),
             str(rec.get("tool_record_id", "")), rec.get("raw_source_file", ""),
             json.dumps(rec, default=str))
            for rec in records
        ]
        self.db.executemany(
            "INSERT INTO raw_findings(id, tool_run_id, tool, kind, tool_record_id,"
            " raw_source_file, record_json) VALUES (?,?,?,?,?,?,?)", rows)
        return len(rows)

    def raw_findings_for_project(self, project_id: str, kind: str | None = None) -> list[dict]:
        sql = ("SELECT rf.*, tr.project_id FROM raw_findings rf"
               " JOIN tool_runs tr ON tr.id = rf.tool_run_id WHERE tr.project_id = ?"
               " AND tr.status = 'ok'")
        params: tuple = (project_id,)
        if kind:
            sql += " AND rf.kind = ?"
            params += (kind,)
        return [dict(r) for r in self.db.query(sql + " ORDER BY rf.id", params)]

    def raw_findings_for_run(self, tool_run_id: str) -> list[dict]:
        rows = self.db.query(
            "SELECT * FROM raw_findings WHERE tool_run_id = ?", (tool_run_id,))
        return [dict(r) for r in rows]

    # ---------------- graph edges ----------------
    def add_edges(self, project_id: str, tool_run_id: str, edges: list[dict]) -> int:
        rows = [
            (_uid(), project_id, e["from"], e["to"], e.get("relation_type", "depends_on"),
             e["evidence_id"], float(e.get("confidence", 1.0)), e.get("source", "static_graph"),
             tool_run_id)
            for e in edges
        ]
        self.db.executemany(
            "INSERT INTO graph_edges(id, project_id, from_component, to_component,"
            " relation_type, evidence_id, confidence, source, tool_run_id)"
            " VALUES (?,?,?,?,?,?,?,?,?)", rows)
        return len(rows)

    def edges_for_project(self, project_id: str) -> list[dict]:
        rows = self.db.query(
            "SELECT * FROM graph_edges WHERE project_id = ?", (project_id,))
        return [dict(r) for r in rows]

    # ---------------- evidence cases ----------------
    def upsert_case(self, case: EvidenceCase) -> None:
        self.db.execute(
            "INSERT INTO evidence_cases(id, project_id, smell_id, smell_type, smell_key,"
            " architecture_type, case_json, created_at) VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(project_id, smell_id) DO UPDATE SET"
            " smell_type = excluded.smell_type, smell_key = excluded.smell_key,"
            " architecture_type = excluded.architecture_type, case_json = excluded.case_json",
            (case.case_id, case.project_id, case.smell_id, case.smell_type, case.smell_key,
             case.architecture_type, json.dumps(case.public_dict()), utcnow()),
        )

    def get_case(self, case_id: str) -> Optional[EvidenceCase]:
        row = self.db.query_one("SELECT * FROM evidence_cases WHERE id = ?", (case_id,))
        if not row:
            return None
        return EvidenceCase.model_validate(json.loads(row["case_json"]))

    def list_cases(self, project_id: str | None = None, split: str | None = None,
                   smell_key: str | None = None) -> list[dict]:
        sql = "SELECT id, project_id, smell_id, smell_type, smell_key, split, created_at FROM evidence_cases WHERE 1=1"
        params: tuple = ()
        if project_id:
            sql += " AND project_id = ?"
            params += (project_id,)
        if split:
            sql += " AND split = ?"
            params += (split,)
        if smell_key:
            sql += " AND smell_key = ?"
            params += (smell_key,)
        return [dict(r) for r in self.db.query(sql + " ORDER BY smell_id", params)]

    def set_case_split(self, case_id: str, split: str) -> None:
        self.db.execute("UPDATE evidence_cases SET split = ? WHERE id = ?", (split, case_id))

    def clear_cases(self, project_id: str) -> None:
        self.db.execute("DELETE FROM evidence_cases WHERE project_id = ?", (project_id,))

    # ---------------- skills ----------------
    def register_skill(self, name: str, version: str, file_path: str, status: str = "production",
                       parent_version: str | None = None, notes: str = "") -> None:
        self.db.execute(
            "INSERT INTO skills(name, version, status, file_path, parent_version, notes, created_at)"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(name, version) DO UPDATE SET status = excluded.status,"
            " file_path = excluded.file_path, notes = excluded.notes",
            (name, version, status, file_path, parent_version, notes, utcnow()),
        )
        self.audit("skill", f"{name}:{version}", f"registered:{status}")

    def get_skill(self, name: str, version: str) -> Optional[dict]:
        row = self.db.query_one(
            "SELECT * FROM skills WHERE name = ? AND version = ?", (name, version))
        return _row_dict(row)

    def list_skills(self, name: str | None = None) -> list[dict]:
        if name:
            rows = self.db.query(
                "SELECT * FROM skills WHERE name = ? ORDER BY created_at", (name,))
        else:
            rows = self.db.query("SELECT * FROM skills ORDER BY name, created_at")
        return [dict(r) for r in rows]

    def production_skill(self, name: str) -> Optional[dict]:
        row = self.db.query_one(
            "SELECT * FROM skills WHERE name = ? AND status = 'production'"
            " ORDER BY created_at DESC LIMIT 1", (name,))
        return _row_dict(row)

    def set_skill_status(self, name: str, version: str, status: str) -> None:
        self.db.execute(
            "UPDATE skills SET status = ? WHERE name = ? AND version = ?",
            (status, name, version))
        self.audit("skill", f"{name}:{version}", f"status:{status}")

    # ---------------- agent runs ----------------
    def save_agent_run(self, run: dict) -> None:
        self.db.execute(
            "INSERT INTO agent_runs(run_id, project_id, case_id, smell_id, agent_mode,"
            " provider, model_id, skill_name, skill_version, prompt_version, evidence_version,"
            " status, suggestion_json, raw_response, prompt_tokens, completion_tokens,"
            " total_tokens, runtime_seconds, repair_attempted, error, structural_checks_json,"
            " experiment_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run["run_id"], run["project_id"], run["case_id"], run.get("smell_id"),
             run["agent_mode"], run.get("provider"), run.get("model_id"),
             run.get("skill_name"), run.get("skill_version"), run.get("prompt_version"),
             run.get("evidence_version"), run["status"], run.get("suggestion_json"),
             run.get("raw_response"), run.get("prompt_tokens"), run.get("completion_tokens"),
             run.get("total_tokens"), run.get("runtime_seconds"),
             int(run.get("repair_attempted", 0)), run.get("error"),
             run.get("structural_checks_json"), run.get("experiment_id"), utcnow()),
        )
        self.audit("agent_run", run["run_id"], f"completed:{run['status']}",
                   details={"mode": run["agent_mode"], "model": run.get("model_id")})

    def get_run(self, run_id: str) -> Optional[dict]:
        return _row_dict(self.db.query_one(
            "SELECT * FROM agent_runs WHERE run_id = ?", (run_id,)))

    def list_runs(self, project_id: str | None = None, agent_mode: str | None = None,
                  status: str | None = None, skill_version: str | None = None,
                  experiment_id: str | None = None, case_ids: list[str] | None = None) -> list[dict]:
        sql = "SELECT * FROM agent_runs WHERE 1=1"
        params: list = []
        if project_id:
            sql += " AND project_id = ?"
            params.append(project_id)
        if agent_mode:
            sql += " AND agent_mode = ?"
            params.append(agent_mode)
        if status:
            sql += " AND status = ?"
            params.append(status)
        if skill_version:
            sql += " AND skill_version = ?"
            params.append(skill_version)
        if experiment_id:
            sql += " AND experiment_id = ?"
            params.append(experiment_id)
        if case_ids:
            sql += f" AND case_id IN ({','.join('?' * len(case_ids))})"
            params.extend(case_ids)
        return [dict(r) for r in self.db.query(sql + " ORDER BY created_at DESC", tuple(params))]

    def save_malformed(self, run_id: str, raw_text: str, error: str) -> None:
        self.db.execute(
            "INSERT INTO malformed_outputs(id, run_id, raw_text, error, created_at)"
            " VALUES (?,?,?,?,?)", (_uid(), run_id, raw_text, error, utcnow()))

    def list_malformed(self, run_id: str | None = None) -> list[dict]:
        if run_id:
            rows = self.db.query("SELECT * FROM malformed_outputs WHERE run_id = ?", (run_id,))
        else:
            rows = self.db.query("SELECT * FROM malformed_outputs ORDER BY created_at DESC")
        return [dict(r) for r in rows]

    def token_stats(self, project_id: str) -> list[dict]:
        rows = self.db.query(
            "SELECT run_id, total_tokens, runtime_seconds FROM agent_runs"
            " WHERE project_id = ? AND total_tokens IS NOT NULL", (project_id,))
        return [dict(r) for r in rows]

    # ---------------- suggested scores ----------------
    def save_suggested_scores(self, run_id: str, source: str, scores: dict) -> None:
        self.db.execute(
            "INSERT INTO suggested_scores(run_id, source, scores_json, created_at)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(run_id, source) DO UPDATE SET scores_json = excluded.scores_json,"
            " created_at = excluded.created_at",
            (run_id, source, json.dumps(scores, default=str), utcnow()))

    def get_suggested_scores(self, run_id: str) -> dict[str, dict]:
        rows = self.db.query(
            "SELECT source, scores_json FROM suggested_scores WHERE run_id = ?", (run_id,))
        return {r["source"]: json.loads(r["scores_json"]) for r in rows}

    # ---------------- reviews ----------------
    def save_review(self, review: HumanReview) -> None:
        self.db.execute(
            "INSERT INTO reviews(review_id, run_id, reviewer_id, evidence_grounding,"
            " refactoring_relevance, architectural_reasoning, minimality_and_safety,"
            " actionability, human_confidence, cost_efficiency, hgrs, would_try_it,"
            " decision, reviewer_notes, edited_output_json, review_timestamp)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(review_id) DO UPDATE SET"
            " evidence_grounding=excluded.evidence_grounding,"
            " refactoring_relevance=excluded.refactoring_relevance,"
            " architectural_reasoning=excluded.architectural_reasoning,"
            " minimality_and_safety=excluded.minimality_and_safety,"
            " actionability=excluded.actionability,"
            " human_confidence=excluded.human_confidence,"
            " cost_efficiency=excluded.cost_efficiency, hgrs=excluded.hgrs,"
            " would_try_it=excluded.would_try_it, decision=excluded.decision,"
            " reviewer_notes=excluded.reviewer_notes,"
            " edited_output_json=excluded.edited_output_json,"
            " review_timestamp=excluded.review_timestamp",
            (review.review_id, review.run_id, review.reviewer_id,
             review.evidence_grounding, review.refactoring_relevance,
             review.architectural_reasoning, review.minimality_and_safety,
             review.actionability, review.human_confidence, review.cost_efficiency,
             review.hgrs, review.would_try_it.value, review.decision.value,
             review.reviewer_notes, review.edited_output_json, review.review_timestamp))
        self.audit("review", review.review_id, "saved", actor=review.reviewer_id,
                   details={"run_id": review.run_id, "hgrs": review.hgrs})

    def review_for_run(self, run_id: str) -> Optional[dict]:
        return _row_dict(self.db.query_one(
            "SELECT * FROM reviews WHERE run_id = ? ORDER BY review_timestamp DESC LIMIT 1",
            (run_id,)))

    def list_reviews(self, project_id: str | None = None) -> list[dict]:
        if project_id:
            rows = self.db.query(
                "SELECT rv.* FROM reviews rv JOIN agent_runs ar ON ar.run_id = rv.run_id"
                " WHERE ar.project_id = ? ORDER BY rv.review_timestamp DESC", (project_id,))
        else:
            rows = self.db.query("SELECT * FROM reviews ORDER BY review_timestamp DESC")
        return [dict(r) for r in rows]

    def reviews_for_skill(self, skill_name: str, skill_version: str) -> list[dict]:
        rows = self.db.query(
            "SELECT rv.*, ar.agent_mode, ar.model_id, ar.total_tokens, ar.runtime_seconds,"
            " ar.structural_checks_json, ar.suggestion_json, ar.case_id, ar.project_id"
            " FROM reviews rv JOIN agent_runs ar ON ar.run_id = rv.run_id"
            " WHERE ar.skill_name = ? AND ar.skill_version = ?",
            (skill_name, skill_version))
        return [dict(r) for r in rows]

    # ---------------- digests / validation ----------------
    def save_digest(self, skill_name: str, skill_version: str, digest: dict) -> str:
        did = _uid()
        self.db.execute(
            "INSERT INTO feedback_digests(id, skill_name, skill_version, digest_json, created_at)"
            " VALUES (?,?,?,?,?)",
            (did, skill_name, skill_version, json.dumps(digest, default=str), utcnow()))
        return did

    def list_digests(self, skill_name: str | None = None) -> list[dict]:
        if skill_name:
            rows = self.db.query(
                "SELECT * FROM feedback_digests WHERE skill_name = ? ORDER BY created_at DESC",
                (skill_name,))
        else:
            rows = self.db.query("SELECT * FROM feedback_digests ORDER BY created_at DESC")
        return [dict(r) for r in rows]

    def save_validation_report(self, skill_name: str, baseline_version: str,
                               candidate_version: str, report: dict, passed: bool) -> str:
        rid = _uid()
        self.db.execute(
            "INSERT INTO validation_reports(id, skill_name, baseline_version,"
            " candidate_version, report_json, passed, created_at) VALUES (?,?,?,?,?,?,?)",
            (rid, skill_name, baseline_version, candidate_version,
             json.dumps(report, default=str), int(passed), utcnow()))
        self.audit("validation", rid, "created",
                   details={"skill": skill_name, "passed": passed})
        return rid

    def get_validation_report(self, report_id: str) -> Optional[dict]:
        return _row_dict(self.db.query_one(
            "SELECT * FROM validation_reports WHERE id = ?", (report_id,)))

    def list_validation_reports(self, skill_name: str | None = None) -> list[dict]:
        if skill_name:
            rows = self.db.query(
                "SELECT * FROM validation_reports WHERE skill_name = ? ORDER BY created_at DESC",
                (skill_name,))
        else:
            rows = self.db.query("SELECT * FROM validation_reports ORDER BY created_at DESC")
        return [dict(r) for r in rows]

    def mark_report(self, report_id: str, human_approved: bool | None = None,
                    promoted: bool | None = None) -> None:
        if human_approved is not None:
            self.db.execute("UPDATE validation_reports SET human_approved = ? WHERE id = ?",
                            (int(human_approved), report_id))
        if promoted is not None:
            self.db.execute("UPDATE validation_reports SET promoted = ? WHERE id = ?",
                            (int(promoted), report_id))

    # ---------------- experiments ----------------
    def create_experiment(self, name: str, config: dict) -> str:
        eid = _uid()
        self.db.execute(
            "INSERT INTO experiments(id, name, config_json, created_at) VALUES (?,?,?,?)",
            (eid, name, json.dumps(config, default=str), utcnow()))
        return eid

    def list_experiments(self) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT * FROM experiments ORDER BY created_at DESC")]
