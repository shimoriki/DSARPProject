# DSARP Refactoring Suggestion Studio

Local-first research platform that turns **Arcan / Designite / dependency-graph
evidence** into evidence-grounded architectural refactoring suggestions,
collects editable **human HGRS reviews**, and improves a versioned text skill
through a **SkillOpt-style feedback loop**. No RAG, no cloud APIs: the primary
model runs locally (Ollama, vLLM, llama.cpp server, or any OpenAI-compatible
endpoint). See [docs/DESIGN.md](docs/DESIGN.md) for architecture, schemas, DB
tables, API endpoints, and milestones.

## Setup

### Windows
```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy config\config.example.yaml config\config.yaml   # then edit
copy .env.example .env                               # optional
```

### Linux / macOS / HPC
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp config/config.example.yaml config/config.yaml
```

### Local model
Point `config/config.yaml → model:` at any of:
- **Ollama**: `provider: ollama`, `base_url: http://localhost:11434`, e.g. `model_id: qwen2.5-coder:7b`
- **vLLM / llama.cpp server / LM Studio**: `provider: openai_compat` (or `llamacpp`), `base_url: http://localhost:8000/v1`
- **HF endpoint** (optional): `provider: hf_endpoint` — a token is only used if set; never required
- **mock**: deterministic offline provider for demos and tests

On a GPU/HPC node, start vLLM (`vllm serve <model> --port 8000`) or llama.cpp
(`llama-server -m model.gguf --port 8080`) and set `base_url` accordingly.

## Reproducible Apache Tika demo (fully offline)

```powershell
py scripts\seed_demo.py          # uses the mock provider; no model needed
streamlit run ui\app.py          # open the console
```

The demo imports sample Arcan/Designite/graph exports from
`sample_data/tika/`, builds normalized evidence, splits train/validation, runs
all three agent modes, and seeds two example reviews. Re-run with a real
model: `py scripts\seed_demo.py --model-provider ollama --model-id qwen2.5-coder:7b`.
Nothing Tika-specific is hardcoded — the demo is just config + sample files.

## CLI

```bash
dsarp project add --name tika --path /path/to/tika --architecture package-based-java
dsarp analyze --project tika --tools arcan,designite        # execute mode
dsarp import --project tika --tool arcan --path exports/ArchitectureSmells.csv
dsarp evidence build --project tika
dsarp evidence split --project tika
dsarp suggest run --project tika --agent tool_evidence --model qwen2.5-coder:7b
dsarp review export --project tika
dsarp skill optimize --skill BreakCyclicDependencySkill_v0
dsarp validate --project tika --skill-v0 v0 --skill-v1 v1_candidate
dsarp promote --report-id <id>            # records human approval, then promotes
dsarp dataset export --min-hgrs 4.0
dsarp experiment run --name exp1 --project tika
dsarp experiment compare --project tika
dsarp serve-api                            # FastAPI on :8600
```

## Console pages
1 Projects · 2 Tool Runs · 3 Evidence Cases · 4 Agent Suggestions ·
5 Human Review (HGRS) · 6 Skill Optimization · 7 Validation Results ·
8 Dataset Export.

Suggested HGRS values come from deterministic checks (+ optional critic agent)
and are always labeled *"Suggested system value — requires human confirmation"*;
reviewers can overwrite every score, comment, and decision.

## SkillOpt loop
reviews → feedback digest → optimizer proposes `skills/<name>_vN_candidate.md`
→ held-out validation (v0 vs candidate, same model, validation split) →
promotion only if: ΔHGRS ≥ 0.10, grounding not decreased, zero critical
hallucinations, **and** recorded human approval. Production skill files are
never overwritten; all versions and reports are kept.

**Skill optimization** updates prompts/skills (default). **Fine-tuning** is an
optional later stage: the Dataset Export page writes JSONL instruction/chat +
CSV datasets and an inert LoRA prep folder — it never trains weights.

## Tools & licensing
Import mode reads existing CSV/JSON/DOT exports. Execute mode shells out to
the commands you configure under `tools:` — DSARP ships **no proprietary
binaries** and assumes you have legal local access to Arcan and Designite.

## Tests
```bash
pytest          # offline; uses the mock provider and temp SQLite DBs
```

## Docker (optional — the app runs fine without it)
```bash
docker compose up      # api on :8600, ui on :8501
```
