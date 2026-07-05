# DSARP Refactoring Suggestion Studio — Design

Local-first research platform that turns Arcan / Designite / dependency-graph
evidence into evidence-grounded architectural refactoring suggestions, collects
editable human HGRS reviews, and improves a versioned text skill through a
SkillOpt-style feedback loop. No RAG, no cloud dependency: the primary model is
a local OpenAI-compatible / Ollama / llama.cpp endpoint.

## 1. Folder structure

```text
DSARP Project/
├── backend/
│   ├── dsarp/
│   │   ├── config.py            # YAML + env configuration
│   │   ├── log.py               # logging setup
│   │   ├── hgrs.py              # HGRS criteria, weights, computation
│   │   ├── registry.py          # smell-category + component-type plugin registry
│   │   ├── models/              # Pydantic schemas
│   │   │   ├── evidence.py      # ToolFinding, DependencyEvidence, EvidenceCase
│   │   │   ├── suggestion.py    # RefactoringSuggestion + agent enums
│   │   │   └── review.py        # HumanReview, decisions
│   │   ├── store/
│   │   │   ├── db.py            # SQLite connection + migration runner
│   │   │   ├── migrations/001_init.sql
│   │   │   └── repos.py         # typed repository layer
│   │   ├── adapters/            # Tool Adapter plugins
│   │   │   ├── base.py          # ToolAdapter ABC + registry, RawSmell/RawEdge
│   │   │   ├── arcan.py         # ArcanAdapter (import + execute command)
│   │   │   ├── designite.py     # DesigniteAdapter
│   │   │   └── static_graph.py  # StaticGraphAdapter (edge lists, SCC cycles)
│   │   ├── normalize.py         # Evidence Normalizer -> EvidenceCase
│   │   ├── providers/           # local model providers
│   │   │   ├── base.py          # ModelProvider protocol + ChatResult
│   │   │   ├── ollama.py        # native Ollama /api/chat
│   │   │   ├── openai_compat.py # vLLM, llama.cpp server, LM Studio
│   │   │   ├── hf_endpoint.py   # optional HF endpoint (token optional)
│   │   │   └── mock.py          # deterministic offline provider (demo/tests)
│   │   ├── agents/
│   │   │   ├── prompts.py       # prompt builders per agent mode, PROMPT_VERSION
│   │   │   ├── runner.py        # run agent, JSON validation, 1 repair attempt
│   │   │   └── critic.py        # optional critic agent (suggested scores only)
│   │   ├── checks.py            # deterministic structural checks -> suggested HGRS
│   │   ├── skillopt/
│   │   │   ├── splits.py        # train/validation split (project-first)
│   │   │   ├── digest.py        # feedback digest from reviews
│   │   │   ├── optimizer.py     # candidate skill generation
│   │   │   └── validate.py      # held-out validation + promotion gate
│   │   ├── exports.py           # JSONL/CSV dataset export + LoRA prep
│   │   ├── services.py          # orchestration used by CLI, API and UI
│   │   ├── api.py               # FastAPI application
│   │   └── cli.py               # `dsarp` Typer CLI
│   └── tests/                   # pytest unit tests (offline, mock provider)
├── ui/
│   ├── app.py                   # Streamlit home/dashboard
│   ├── _bootstrap.py            # sys.path + shared context helpers
│   └── pages/1..8_*.py          # Projects, Tool Runs, Evidence Cases,
│                                # Agent Suggestions, Human Review,
│                                # Skill Optimization, Validation, Dataset Export
├── skills/                      # versioned Markdown skills (never overwritten)
│   └── BreakCyclicDependencySkill_v0.md
├── data/                        # evidence db, raw imports, exports, reports
├── config/
│   ├── config.example.yaml      # model endpoint, tool commands, weights
│   └── projects/tika.yaml       # Apache Tika demo configuration
├── sample_data/tika/            # sample Arcan/Designite/graph exports
├── scripts/seed_demo.py         # reproducible offline Tika demo
├── docs/DESIGN.md
├── Dockerfile / docker-compose.yml (optional; app runs without Docker)
├── pyproject.toml / requirements.txt / .env.example / README.md
```

## 2. Data schemas (Pydantic)

### EvidenceCase (normalized evidence, tool-agnostic)
```json
{
  "case_id": "sha1-of(project, smell)",
  "project_id": "apache-tika",
  "source_revision": "optional-git-commit",
  "architecture_type": "package-based-java",
  "component_type": "package | module | class | service | bounded_context | deployment_unit",
  "smell_id": "ARCAN_CD_001",
  "smell_type": "Cyclic Dependency",
  "affected_components": ["org.example.a", "org.example.b"],
  "tool_findings": [{"tool": "arcan", "tool_record_id": "...", "evidence_id": "ARCAN_CD_001",
                     "raw_source_file": "ArchitectureSmells.csv", "attributes": {"severity": "high"}}],
  "dependency_evidence": [{"from": "a", "to": "b", "relation_type": "depends_on",
                           "evidence_id": "GRAPH_EDGE_002", "confidence": 1.0, "source": "static_graph"}],
  "metrics": [],
  "limitations": ["Exact source-level call direction is unavailable."]
}
```
Evidence rule: the system never claims a class/method/edge/direction unless the
exact fact exists in normalized evidence; otherwise "Requires source inspection."

### RefactoringSuggestion (agent output — strict JSON, Pydantic-validated)
Fields exactly as specified in the requirements (run_id, agent_mode,
evidence_used, observed_tool_evidence, candidate_boundary_to_inspect with
edge_direction_status, recommended_refactoring enum, implementation_steps,
risks_and_tradeoffs, confidence 0..1, limitations, ...). One repair attempt for
invalid JSON; malformed outputs stored separately, never silently fixed.

### HumanReview
Seven 1–5 criteria + computed HGRS + would_try_it + decision + notes +
optional human-edited preferred output.

HGRS = 0.25·grounding + 0.20·relevance + 0.15·reasoning + 0.15·minimality
     + 0.10·actionability + 0.10·human_confidence + 0.05·cost_efficiency

## 3. Execution flow

```text
1. dsarp project add            -> projects row
2. dsarp import / analyze       -> tool_runs + raw_findings (+ graph_edges)
   (import mode reads CSV/JSON/TXT/XML/DOT exports; execute mode shells out to
    configured local Arcan/Designite commands — user must own licenses)
3. dsarp evidence build         -> Evidence Normalizer merges raw findings
                                   across tools into EvidenceCase rows with
                                   provenance + limitations
4. dsarp evidence split         -> train/validation assignment (project-first,
                                   never the same smell instance in both)
5. dsarp suggest run            -> Agent Runner (baseline | skill | tool_evidence)
                                   via local model provider; strict JSON; tokens
                                   + runtime + skill/prompt versions tracked;
                                   deterministic structural checks stored
6. Streamlit Human Review       -> suggested HGRS values (deterministic checks
                                   + optional critic) clearly labeled, human
                                   edits every field; audit trail
7. dsarp skill optimize         -> feedback digest -> optimizer agent writes
                                   skills/<name>_v<N+1>_candidate.md
8. dsarp validate               -> run v0 vs candidate on held-out cases,
                                   compare HGRS (human where available, else
                                   labeled proxy), promotion gate + human
                                   approval; production skill never overwritten
9. dsarp dataset export         -> JSONL instruction / JSONL chat / CSV from
                                   reviewed high-quality examples (+ LoRA prep)
```

## 4. Database tables (SQLite)

| table | purpose |
|---|---|
| projects | id, name, path, architecture_type, source_revision |
| tool_runs | tool, mode (import/execute), source_path, command, source_hash, status, timestamps |
| raw_findings | raw tool records (kind: smell/edge/metric) kept separate from normalized evidence |
| graph_edges | normalized dependency edges with evidence_id, confidence, source |
| evidence_cases | normalized EvidenceCase JSON + split (train/validation/unassigned) |
| skills | (name, version) -> file_path, status: production/candidate/archived/rejected |
| agent_runs | run_id, case, mode, provider/model, skill+prompt+evidence versions, status, suggestion JSON, tokens, runtime, structural checks |
| malformed_outputs | invalid model responses stored verbatim |
| suggested_scores | per-run suggested HGRS values, source: deterministic/critic |
| reviews | human HGRS review incl. edited preferred output and decision |
| feedback_digests | aggregated review feedback per skill version |
| validation_reports | v0 vs candidate held-out comparison, passed/approved/promoted flags |
| experiments | experiment configs; agent_runs carry experiment_id |
| audit_log | every agent run, review edit, promotion, export |
| schema_migrations | applied migration versions |

## 5. API endpoints (FastAPI, mirrors services used by CLI/UI)

```text
GET  /health
GET/POST /projects                         list / add project
POST /projects/{name}/import               import a tool export file
POST /projects/{name}/analyze              execute configured local tools
POST /projects/{name}/evidence/build       normalize evidence
POST /projects/{name}/evidence/split       assign train/validation
GET  /projects/{name}/cases[?split=]       list evidence cases
GET  /cases/{case_id}                      full normalized case
POST /suggest                              run agent on cases
GET  /runs[?project=&mode=]  GET /runs/{run_id}
GET  /runs/{run_id}/suggested-scores       deterministic + critic suggestions
POST /reviews                GET /reviews  save / list human reviews
GET  /skills                 POST /skills/{name}/optimize
POST /skills/{name}/validate               held-out v0 vs candidate
POST /validation/{report_id}/approve       record human approval + promote
GET  /experiments/compare                  comparison table
POST /export/dataset                       JSONL/CSV export
```

## 6. Implementation milestones

1. **M1 — Evidence foundation**: config, SQLite schema/migrations, Pydantic
   models, Arcan/Designite/StaticGraph import adapters, normalizer, Tika sample
   data, unit tests.
2. **M2 — Agents**: model provider abstraction (Ollama/vLLM/llama.cpp/HF/mock),
   three agent modes, strict JSON validation + single repair, run telemetry.
3. **M3 — Review console**: deterministic checks + optional critic for
   suggested HGRS, Streamlit console (8 pages), audit trail.
4. **M4 — SkillOpt loop**: splits, feedback digest, optimizer agent, held-out
   validation, gated promotion with mandatory human approval.
5. **M5 — Research tooling**: experiment/comparison mode, dataset exports +
   LoRA prep, CLI, FastAPI, README, Docker (optional), reproducible Tika demo.

MVP focuses on Cyclic Dependency; smell categories and component types are
registries, so new smells/architectures are added without schema redesign.
