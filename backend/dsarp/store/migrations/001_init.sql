CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    path TEXT,
    architecture_type TEXT NOT NULL DEFAULT 'package-based-java',
    component_type TEXT NOT NULL DEFAULT 'package',
    source_revision TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    tool TEXT NOT NULL,
    mode TEXT NOT NULL,                -- import | execute
    source_path TEXT,
    command TEXT,
    source_hash TEXT,
    status TEXT NOT NULL,              -- ok | error
    error TEXT,
    started_at TEXT,
    finished_at TEXT,
    meta_json TEXT
);

CREATE TABLE IF NOT EXISTS raw_findings (
    id TEXT PRIMARY KEY,
    tool_run_id TEXT NOT NULL REFERENCES tool_runs(id),
    tool TEXT NOT NULL,
    kind TEXT NOT NULL,                -- smell | edge | metric
    tool_record_id TEXT,
    raw_source_file TEXT,
    record_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_edges (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    from_component TEXT NOT NULL,
    to_component TEXT NOT NULL,
    relation_type TEXT NOT NULL DEFAULT 'depends_on',
    evidence_id TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    source TEXT NOT NULL,
    tool_run_id TEXT
);

CREATE TABLE IF NOT EXISTS evidence_cases (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(name),
    smell_id TEXT NOT NULL,
    smell_type TEXT NOT NULL,
    smell_key TEXT NOT NULL DEFAULT 'custom_tool_smell',
    architecture_type TEXT,
    split TEXT NOT NULL DEFAULT 'unassigned',   -- train | validation | unassigned
    case_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, smell_id)
);

CREATE TABLE IF NOT EXISTS skills (
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL,              -- production | candidate | archived | rejected
    file_path TEXT NOT NULL,
    parent_version TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (name, version)
);

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    case_id TEXT NOT NULL REFERENCES evidence_cases(id),
    smell_id TEXT,
    agent_mode TEXT NOT NULL,
    provider TEXT,
    model_id TEXT,
    skill_name TEXT,
    skill_version TEXT,
    prompt_version TEXT,
    evidence_version TEXT,
    status TEXT NOT NULL,              -- ok | invalid_json | error
    suggestion_json TEXT,
    raw_response TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    runtime_seconds REAL,
    repair_attempted INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    structural_checks_json TEXT,
    experiment_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS malformed_outputs (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    raw_text TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS suggested_scores (
    run_id TEXT NOT NULL,
    source TEXT NOT NULL,              -- deterministic | critic
    scores_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, source)
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(run_id),
    reviewer_id TEXT NOT NULL,
    evidence_grounding INTEGER NOT NULL,
    refactoring_relevance INTEGER NOT NULL,
    architectural_reasoning INTEGER NOT NULL,
    minimality_and_safety INTEGER NOT NULL,
    actionability INTEGER NOT NULL,
    human_confidence INTEGER NOT NULL,
    cost_efficiency INTEGER NOT NULL,
    hgrs REAL NOT NULL,
    would_try_it TEXT NOT NULL,
    decision TEXT NOT NULL,
    reviewer_notes TEXT,
    edited_output_json TEXT,
    review_timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback_digests (
    id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL,
    skill_version TEXT NOT NULL,
    digest_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS validation_reports (
    id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL,
    baseline_version TEXT NOT NULL,
    candidate_version TEXT NOT NULL,
    report_json TEXT NOT NULL,
    passed INTEGER NOT NULL,
    human_approved INTEGER NOT NULL DEFAULT 0,
    promoted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    name TEXT,
    config_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    action TEXT NOT NULL,
    actor TEXT,
    details_json TEXT,
    at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_project ON agent_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_runs_case ON agent_runs(case_id);
CREATE INDEX IF NOT EXISTS idx_reviews_run ON reviews(run_id);
CREATE INDEX IF NOT EXISTS idx_edges_project ON graph_edges(project_id);
CREATE INDEX IF NOT EXISTS idx_cases_project ON evidence_cases(project_id);
