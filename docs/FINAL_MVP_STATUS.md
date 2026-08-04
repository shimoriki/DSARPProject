# DSARP — Final MVP Status

Snapshot after the "make it complete + multi-repository generalisation" continuation.
Verified with `py` (Python 3.13.5) on Windows; offline-first, no cloud.

## What works locally (no proprietary tools, no cloud)

- **Full pipeline**: evidence → candidates → repo-independent features → ranker →
  token-optimised LLM explanation → OpenRewrite draft → 8 no-hallucination validators →
  ranked schema-valid suggestions + token report.
- **SQLite backend** (`dsarp/db`): `db init|status|import-outputs`; indexes projects, tool
  runs, suggestions, graphs, HGRS, token reports. UI/API read DB or files.
- **Source index** (`dsarp/source_index`): regex Java indexer → file/class/method/package +
  import-edge graph; powers real entity validation.
- **Graph builder**: cycles, SCC, fan-in/out, instability, betweenness, **graph slices**,
  revision hash for caching.
- **Multi-repository**: split manager + leakage guard, repo-independent structural features,
  name masking (Component_A/B/C), multi-repo dataset builder, ranker training with
  **leave-one-repository-out** validation, feature importance, overfitting warning, versioned
  metadata, generalisation report (md/json/csv).
- **Unseen-repo inference**: `repo add` + `evaluate --name`, or `evaluate --repo-url`; build-system
  detection, tool-absence fallback (source index + import graph) with transparency.
- **Model UX**: `model list`, `model smoke-test`, `--model offline|ollama|llamacpp|openai|vllm`.
  Ollama verified live (`qwen2.5-coder:3b`); offline provider always available.
- **OpenRewrite**: draft/plan generation + `recipes validate` (never marks `validated` without
  real dry-run+build).
- **Insights** (Task 15, 8 features): health radar, evidence-conflict detector, pattern library,
  active-learning queue, readiness score, recipe risk meter, graph-delta preview, issue/PR draft,
  no-hallucination leaderboard.
- **FastAPI backend** (11 endpoints) — schema-valid, other agents can consume.
- **20-page Streamlit dashboard**.
- **`demo full`** runs the entire local MVP end-to-end.
- **Tests**: 23 passing (`pytest -q`), all suggestions schema-valid, examples validate.

## What works on HPC (scripts provided, parameterised)

- Slurm: `serve_vllm`, `mine_all_repos`, `build_dataset`, `train_ranker`, `train_lora_optional`,
  `evaluate_cassandra`, `full_pipeline_hpc`, plus legacy scripts. All use env vars for
  account/partition/GPU; no hardcoded user paths.
- `dsarp-hpc demo plan` (prints plan, submits nothing) / `demo submit --yes` (guarded; needs sbatch).
- vLLM provider + resolve for Qwen2.5-Coder 7B/14B/32B, multi-GPU tensor parallel.

## Import-mode only until binaries provided

- **Arcan / Designite / RefactoringMiner**: import mode is fully wired (parses real exports).
  Execute mode runs the configured JVM command and records status/logs but returns **no
  evidence on failure/missing binary** (never fabricates). Provide the binaries + set the
  `command`/`executable_path` in `configs/hpc.yaml` (or local) to enable.

## Requires external tools / GPU

- Real smell mining at scale → Arcan/Designite/RefactoringMiner JARs (JVM).
- OpenRewrite `validated` status → Maven + OpenRewrite in the repo.
- vLLM serving + LoRA → GPU node (LoRA also needs peft/torch/transformers; guarded, MVP-optional).

## Known limitations

- Fixtures are synthetic (structurally realistic, distinct namespaces) so LORO shows perfect
  separation; real repos will show a spread. Stage real tool exports for real numbers.
- Source indexer is regex-based (conservative); tree-sitter optional. `cohesion`/`ATDI` features
  are placeholders (0.0) until a deeper parse or tool metric is supplied.
- No auth on the FastAPI backend (local dev only).

## Exact demo commands

```bash
py -m pip install -e .[local]           # or: pip install pydantic PyYAML networkx jsonschema requests scikit-learn streamlit
dsarp-local demo full                   # whole local MVP, offline
dsarp-local ui                          # dashboard at http://localhost:8501
dsarp-local model smoke-test --model offline
dsarp-local dataset build-multi-repo && dsarp-local ranker train \
    --dataset data/training/multi_repo_train_candidates.jsonl
dsarp-local validate leave-one-repo-out
dsarp-local repo add --name my --path /path/to/java/repo && dsarp-local evaluate --name my --model offline
dsarp-local evaluate cassandra --with-normalize            # final unseen test
dsarp-local generalisation report
dsarp-local api serve                    # FastAPI at http://127.0.0.1:8000/docs
dsarp-hpc demo plan                      # HPC plan (submits nothing)
```

## Next research experiments

- Stage real RefactoringMiner + Arcan/Designite exports for the 9 training repos → real alignment
  labels → measure true LORO recall per smell/refactoring type.
- Compare providers on the no-hallucination leaderboard (offline vs Ollama vs vLLM).
- Add class-level graphs from the source index; learn edge-direction from imports.
- Optional LoRA once the masked chat dataset exceeds the guard threshold (200 examples).
