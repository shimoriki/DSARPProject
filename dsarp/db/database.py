"""SQLite connection management + init/status."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from .migrations import SCHEMA_VERSION, migrate


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init(self) -> int:
        with self.connect() as conn:
            return migrate(conn)

    def status(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"exists": False, "path": str(self.path)}
        with self.connect() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            counts: Dict[str, int] = {}
            for t in tables:
                if t in ("schema_meta", "sqlite_sequence"):
                    continue
                counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            ver_row = conn.execute("SELECT version FROM schema_meta").fetchone()
        return {
            "exists": True, "path": str(self.path),
            "schema_version": ver_row[0] if ver_row else None,
            "expected_version": SCHEMA_VERSION,
            "row_counts": counts,
        }

    def tables(self) -> List[str]:
        with self.connect() as conn:
            return [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
