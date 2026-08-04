# DSARP Evidence-Based Refactoring Agent

Modular, **evidence-grounded** Java refactoring-suggestion system. It learns from real
historical refactorings (RefactoringMiner), combines them with architecture-smell evidence
(Arcan, Designite, dependency graphs, static analysis), and emits **ranked, schema-valid,
no-hallucination** refactoring suggestions for unseen repositories — with a human-review UI.

> No cloud APIs by default. Local mode is offline-first; HPC mode adds vLLM + optional LoRA.

See [`docs/DESIGN.md`](docs/DESIGN.md) for the architecture, graph-of-loops, schemas, and plans,
and [`CLAUDE.md`](CLAUDE.md) for the governing token + no-hallucination policy.

## Quickstart (local, offline)

```bash
py -m pip install -e .[local]         # or: pip install pydantic PyYAML networkx jsonschema requests scikit-learn streamlit
dsarp-local demo full                 # ← runs the WHOLE local MVP end-to-end, offline
dsarp-local ui                        # Streamlit dashboard at http://localhost:8501
```

Or step by step:

```bash
py scripts/make_sample_data.py apache-cassandra     # stage sample tool exports via real adapters
dsarp-local normalize --repo apache-cassandra --revision demo
dsarp-local suggest   --repo apache-cassandra --top-k 3
```

Outputs land in `data/outputs/<repo>/` (`suggestions.json`, `report.json`). Every suggestion
validates against [`docs/schemas/suggestion_schema.json`](docs/schemas/suggestion_schema.json).

## Multi-repository generalisation

Trains on many repos with **repository-independent structural features** (no raw package names),
validates with **leave-one-repository-out**, and evaluates on **unseen** repos. Cassandra is the
final unseen test only — a leakage guard blocks it from every training split.

```bash
py scripts/make_multi_repo_fixtures.py              # synthetic multi-repo fixtures (distinct namespaces)
dsarp-local dataset build-multi-repo --splits train
dsarp-local ranker train --dataset data/training/multi_repo_train_candidates.jsonl
dsarp-local validate leave-one-repo-out
dsarp-local generalisation report                   # docs/GENERALISATION_REPORT.md + json/csv

# Any new/unseen repository:
dsarp-local repo add --name my-project --path /path/to/repo
dsarp-local evaluate --name my-project --model offline
# or by URL: dsarp-local evaluate --repo-url https://github.com/org/name --name name
```

Splits: [`configs/repos_train.yaml`](configs/repos_train.yaml) ·
[`repos_validation.yaml`](configs/repos_validation.yaml) ·
[`repos_test.yaml`](configs/repos_test.yaml) ·
[`repos_unseen.yaml`](configs/repos_unseen.yaml) (Cassandra).

## CLI (local == `dsarp-local`, HPC == `dsarp-hpc`)

| Command | Loop | Purpose |
|---|---|---|
| `setup` | — | create `data/` tree |
| `repo clone --repo <slug>` | 1 | clone/update (git optional) |
| `tools import --repo <r> --tool <arcan\|designite> --path <export>` | 4 | import tool findings |
| `graph build --repo <r> --edges <json>` | 5 | build dependency graph + metrics |
| `normalize --repo <r>` | 6 | merge findings+graph → `EvidenceCase` |
| `ranker train --dataset <jsonl>` | 8 | train local preference ranker |
| `source index --repo <r>` | 6 | build Java source index for entity validation |
| `dataset build-multi-repo` | 7 | masked multi-repo ranker dataset |
| `ranker train --dataset <j>` | 8 | train ranker (repo-independent features) |
| `validate leave-one-repo-out` | 8 | LORO generalisation validation |
| `suggest --repo <r> [--model]` | 9-13 | ranked, validated suggestions + token report |
| `recipes validate --repo <r>` | 11 | OpenRewrite dry-run/build (never fakes `validated`) |
| `evaluate cassandra [--dry-run]` | 9-13 | final unseen-test workflow (leakage-guarded) |
| `evaluate --name <r> \| --repo-url <u>` | 9-13 | inference on any unseen repo |
| `generalisation report` | 13 | cross-repo generalisation report |
| `insights <kind> --repo <r>` | 15 | health/conflicts/patterns/readiness/issue-draft |
| `model list \| smoke-test` | — | local model management |
| `db init \| status \| import-outputs` | — | SQLite persistence |
| `api serve` | — | FastAPI backend (other agents) |
| `demo full` / `demo plan\|submit` | — | end-to-end local demo / HPC plan |
| `ui` | — | launch dashboard (20 pages) |

## What's implemented

- **Core pipeline** (M1–M14): schemas, config profiles, repo manager, tool adapters (import mode),
  RefactoringMiner adapter, graph builder, evidence normalizer, alignment (with confidence),
  dataset builder, deterministic candidate generator, preference ranker, LLM explanation agent,
  OpenRewrite recipe generator, 8 no-hallucination validators, 12-page Streamlit UI, CLI.
- **Token-optimisation layer**: 4 context levels, context packages, hash cache, `TokenBudgetManager`,
  per-run optimisation report, compact project-memory files.
- **HPC** (M15): Slurm scripts for mining, dataset, LoRA, Cassandra eval; vLLM provider.
- **Tests**: end-to-end + unit (`pytest tests/`).

## Model providers (no cloud by default)

`offline` (deterministic, network-free — default) · `ollama` · `llamacpp` · `openai`-compatible · `vllm` (HPC).
Set in `configs/local.yaml` / `configs/hpc.yaml` under `model_provider`.

## Guardrails

- Java tools (Arcan/Designite/RefactoringMiner) run in **import mode** locally and **execute mode** on
  HPC; execute stubs return empty rather than fabricating findings — missing evidence ⇒
  `requires_source_inspection`.
- `apache/cassandra` is the **only** unseen test repo and is absent from every training config.
- OpenRewrite recipes stay `draft` until dry-run/build/tests pass.
