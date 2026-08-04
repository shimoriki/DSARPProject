# DSARP API Contract

Stable HTTP surface (FastAPI, `dsarp-local api serve`). All bodies are the same
schema-valid objects the CLI/UI use (`docs/schemas/`, `dsarp/schemas.py`).

Base URL (local): `http://127.0.0.1:8000`

| Method | Path | Purpose | Returns |
|---|---|---|---|
| GET  | `/projects` | list projects with evidence | `[{project_id, revision, smells}]` |
| GET  | `/tool-runs?project_id=` | tool run provenance (DB) | `[tool_run]` |
| GET  | `/evidence-cases` | normalized evidence cases | `[EvidenceCase]` |
| GET  | `/suggestions?project_id=` | ranked suggestions | `[Suggestion]` |
| GET  | `/suggestions/{id}?project_id=` | one suggestion | `Suggestion` |
| POST | `/suggestions/run` | run inference | `{project_id, suggestions, grounding}` |
| POST | `/reviews` | submit HGRS review | `{review_id, weighted_score}` |
| GET  | `/reports/token?project_id=` | token optimisation report | `token_report` |
| GET  | `/reports/cassandra` | Cassandra final-test report | `report` |
| GET  | `/recipes?project_id=` | OpenRewrite recipe plans | `[recipe_plan]` |
| POST | `/recipes/validate?project_id=` | validate recipes | `{status_counts}` |

### Request bodies

`POST /suggestions/run`
```json
{ "project_id": "apache-cassandra", "top_k": 3, "model": "offline" }
```
`model` ∈ `offline | ollama | llamacpp | openai | vllm | ollama:<model>` (optional; omit for config default).

`POST /reviews`
```json
{ "suggestion_id": "…", "project_id": "apache-cassandra", "reviewer": "alice",
  "scores": {"evidence_grounding": 0.8, "refactoring_relevance": 0.7, "…": 0.6},
  "would_try_it": true, "preferred": true, "notes": "…" }
```

### Guarantees

- Every `Suggestion` validates against `docs/schemas/suggestion_schema.json`.
- `evidence_used` references real evidence IDs; unproven entities are demoted to
  `requires_source_inspection` (never invented).
- Recipes are never `validated` unless dry-run + build actually passed.
- Cassandra is unseen-test only; training endpoints refuse it (leakage guard).

See `examples/*.example.json` for concrete instances and `docs/inter_agent_protocol.md`
for the multi-step agent flow.
