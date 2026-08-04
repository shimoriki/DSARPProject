"""Versioned schema DDL. Idempotent — safe to run repeatedly.

Complex objects are stored as JSON in a `payload` column with a few promoted,
indexed columns for querying. This keeps the schema stable as models evolve.
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 2

DDL = [
    # repositories & splits ------------------------------------------------ #
    """CREATE TABLE IF NOT EXISTS repositories (
        project_id TEXT PRIMARY KEY,
        repo_url TEXT, local_path TEXT, split TEXT,
        revision TEXT, commit_count INTEGER, updated_at TEXT, payload TEXT
    )""",
    # tool runs (arcan/designite/refactoringminer) ------------------------- #
    """CREATE TABLE IF NOT EXISTS tool_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT, tool TEXT, mode TEXT, status TEXT,
        command TEXT, version TEXT, revision TEXT,
        finding_count INTEGER, output_path TEXT, log_path TEXT,
        created_at TEXT, payload TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS refactoring_events (
        event_id TEXT PRIMARY KEY, project_id TEXT, commit_sha TEXT,
        refactoring_type TEXT, payload TEXT
    )""",
    # evidence, graph ------------------------------------------------------ #
    """CREATE TABLE IF NOT EXISTS evidence_cases (
        case_id TEXT PRIMARY KEY, project_id TEXT, revision TEXT,
        smell_count INTEGER, created_at TEXT, payload TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS graph_metadata (
        project_id TEXT, revision TEXT, graph_hash TEXT,
        node_count INTEGER, edge_count INTEGER, cycle_count INTEGER,
        scc_count INTEGER, created_at TEXT, payload TEXT,
        PRIMARY KEY (project_id, revision)
    )""",
    # candidates, suggestions, validation --------------------------------- #
    """CREATE TABLE IF NOT EXISTS candidates (
        candidate_id TEXT PRIMARY KEY, project_id TEXT, smell_id TEXT,
        refactoring_type TEXT, payload TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS suggestions (
        suggestion_id TEXT PRIMARY KEY, case_id TEXT, project_id TEXT,
        revision TEXT, rank INTEGER, score REAL, confidence REAL,
        smell_type TEXT, refactoring_type TEXT, verification_status TEXT,
        recipe_status TEXT, created_at TEXT, payload TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS validation_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        suggestion_id TEXT, ok INTEGER, unsupported_count INTEGER, payload TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS recipes (
        recipe_id TEXT PRIMARY KEY, suggestion_id TEXT, project_id TEXT,
        recipe_type TEXT, recipe_status TEXT, recipe_path TEXT, payload TEXT
    )""",
    # human review, reports, model runs ----------------------------------- #
    """CREATE TABLE IF NOT EXISTS hgrs_reviews (
        review_id TEXT PRIMARY KEY, suggestion_id TEXT, project_id TEXT,
        reviewer TEXT, weighted_score REAL, would_try_it INTEGER,
        preferred INTEGER, created_at TEXT, payload TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS token_reports (
        run_id TEXT PRIMARY KEY, project_id TEXT, total_model_calls INTEGER,
        cache_hits INTEGER, estimated_tokens_saved INTEGER, created_at TEXT, payload TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS model_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, name TEXT,
        version TEXT, metrics TEXT, created_at TEXT, payload TEXT
    )""",
    # indexes -------------------------------------------------------------- #
    "CREATE INDEX IF NOT EXISTS idx_sug_project ON suggestions(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_tool_project ON tool_runs(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_rev_project ON refactoring_events(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_hgrs_sug ON hgrs_reviews(suggestion_id)",
]


def migrate(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER)")
    for stmt in DDL:
        cur.execute(stmt)
    row = cur.execute("SELECT version FROM schema_meta").fetchone()
    if row is None:
        cur.execute("INSERT INTO schema_meta (version) VALUES (?)", (SCHEMA_VERSION,))
    else:
        cur.execute("UPDATE schema_meta SET version = ?", (SCHEMA_VERSION,))
    conn.commit()
    return SCHEMA_VERSION
