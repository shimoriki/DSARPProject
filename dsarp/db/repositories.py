"""Store — DAO over the SQLite backend. UPSERT-based, JSON-payload aware."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .database import Database
from . import models as M


class Store:
    def __init__(self, db_path: Path):
        self.db = Database(db_path)

    def init(self) -> int:
        return self.db.init()

    def status(self) -> Dict[str, Any]:
        return self.db.status()

    # -- generic upsert ---------------------------------------------------- #
    def _upsert(self, table: str, row: Dict[str, Any], pk: str) -> None:
        cols = list(row.keys())
        pk_cols = [c.strip() for c in pk.split(",")]
        placeholders = ",".join("?" for _ in cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in pk_cols)
        sql = (f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) "
               f"ON CONFLICT({pk}) DO UPDATE SET {updates}")
        with self.db.connect() as conn:
            conn.execute(sql, [row[c] for c in cols])
            conn.commit()

    def _insert(self, table: str, row: Dict[str, Any]) -> None:
        cols = list(row.keys())
        sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})"
        with self.db.connect() as conn:
            conn.execute(sql, [row[c] for c in cols])
            conn.commit()

    # -- writers ----------------------------------------------------------- #
    def save_repository(self, **kw) -> None:
        table, row = M.repository_row(**kw)
        self._upsert(table, row, "project_id")

    def save_tool_run(self, **kw) -> None:
        table, row = M.tool_run_row(**kw)
        self._insert(table, row)

    def save_suggestions(self, suggestions: List[Dict[str, Any]]) -> int:
        n = 0
        for s in suggestions:
            table, row = M.suggestion_row(s)
            self._upsert(table, row, "suggestion_id")
            n += 1
        return n

    def save_hgrs(self, review: Dict[str, Any], project_id: str = "") -> None:
        table, row = M.hgrs_row(review, project_id)
        self._upsert(table, row, "review_id")

    def save_token_report(self, report: Dict[str, Any]) -> None:
        table, row = M.token_report_row(report)
        if row.get("run_id"):
            self._upsert(table, row, "run_id")

    def save_model_run(self, kind: str, name: str, version: str = "",
                       metrics: Dict | None = None) -> None:
        table, row = M.model_run_row(kind, name, version, metrics)
        self._insert(table, row)

    def save_evidence_case(self, case: Dict[str, Any]) -> None:
        row = {"case_id": case["case_id"], "project_id": case.get("project_id"),
               "revision": case.get("revision"), "smell_count": len(case.get("smells", [])),
               "created_at": M.now_iso(), "payload": json.dumps(case, default=str)}
        self._upsert("evidence_cases", row, "case_id")

    def save_graph_metadata(self, project_id: str, revision: str, graph_hash: str,
                            metrics: Dict[str, Any]) -> None:
        row = {"project_id": project_id, "revision": revision, "graph_hash": graph_hash,
               "node_count": metrics.get("node_count", 0),
               "edge_count": metrics.get("edge_count", 0),
               "cycle_count": metrics.get("cycle_count", 0),
               "scc_count": metrics.get("scc_count", 0),
               "created_at": M.now_iso(), "payload": json.dumps(metrics, default=str)}
        self._upsert("graph_metadata", row, "project_id, revision")

    # -- readers ----------------------------------------------------------- #
    def _rows(self, sql: str, params=()) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def list_projects(self) -> List[Dict[str, Any]]:
        return self._rows("SELECT * FROM repositories ORDER BY project_id")

    def list_suggestions(self, project_id: str) -> List[Dict[str, Any]]:
        rows = self._rows(
            "SELECT payload FROM suggestions WHERE project_id=? ORDER BY rank", (project_id,))
        return [json.loads(r["payload"]) for r in rows]

    def list_tool_runs(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if project_id:
            return self._rows("SELECT * FROM tool_runs WHERE project_id=? ORDER BY id DESC",
                              (project_id,))
        return self._rows("SELECT * FROM tool_runs ORDER BY id DESC")

    def list_hgrs(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if project_id:
            return self._rows("SELECT * FROM hgrs_reviews WHERE project_id=?", (project_id,))
        return self._rows("SELECT * FROM hgrs_reviews")

    def list_model_runs(self) -> List[Dict[str, Any]]:
        return self._rows("SELECT * FROM model_runs ORDER BY id DESC")
