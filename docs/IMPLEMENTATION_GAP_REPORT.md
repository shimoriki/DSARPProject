# DSARP Implementation Gap Report

Baseline audit before the "make it complete" continuation. Concise by policy.

## Implemented (working)

- **Schemas** (`dsarp/schemas.py`) — EvidenceCase, Suggestion, ContextPackage, HGRSReview; mirror `docs/schemas/`.
- **Config** (`dsarp/config.py`) — local/hpc YAML profiles, repo lists.
- **Repo manager** (`dsarp/repositories/manager.py`) — clone/status/commits, git-optional.
- **Tool adapters** (`dsarp/tools/*`) — Arcan/Designite **import mode** real; execute() returns `[]` (stub).
- **RefactoringMiner** (`dsarp/mining/refactoring_miner.py`) — import mode real; execute() stub.
- **Graph builder** (`dsarp/graphs/builder.py`) — package graph, cycles, SCC, fan-in/out, betweenness, summary.
- **Normalizer** (`dsarp/evidence/normalizer.py`) — tool-agreement merge + graph-cycle smells.
- **Aligner** (`dsarp/alignment/aligner.py`) — confidence-scored, no "every refactoring fixes a smell" assumption.
- **Dataset** (`dsarp/dataset/builder.py`) — ranker rows + chat, name masking.
- **Candidates** (`dsarp/candidates/generator.py`) — deterministic catalogue per smell family.
- **Ranker** (`dsarp/ranking/ranker.py`) — deterministic + sklearn/LightGBM fallback.
- **Explainer** (`dsarp/agents/explainer.py`) — context package, budget, cache; offline/Ollama tested.
- **OpenRewrite** (`dsarp/openrewrite/generator.py`) — draft YAML/visitor/manual plans.
- **Validators** (`dsarp/validation/validators.py`) — 8 validators; demote-only.
- **Pipeline/CLI** — end-to-end suggest; token report. **12-page UI**. **Slurm** scripts. **8 tests** green.

## Stubbed / thin

- Tool + RefactoringMiner **execute mode** (JVM) — return empty, no subprocess wiring.
- **Ranker features** — only 5 (`catalogue_rank, graph_delta, risk, tool_agreement, severity`); not repo-independent structural set.
- **LoRA** — plan-only script.
- **OpenRewrite validation** — no dry-run/compile command.
- **Source index** — schema field exists, no builder; validators can't check entities.

## Missing

- **SQLite persistence** (Task 2) — everything is file-only.
- **Source indexer** (Task 6).
- **Graph slices + revision cache** (Task 7).
- **Multi-repo split manager, LORO validation, repo-independent features, generalisation report** (addendum).
- **Model `list`/`smoke-test`, `--model` flag** (Task 10).
- **FastAPI backend** (Task 16).
- **Inter-agent docs + examples** (Task 17).
- **`demo full` / `demo plan|submit`** (Tasks 18-19).
- **Creative features** (Task 15).
- **Generic unseen-repo `repo add` + evaluate-by-url** (addendum 5).

## Mode gaps

- **Local**: SQLite, source index, model UX, demo, richer UI. No cloud needed.
- **HPC**: only 4 slurm scripts; need serve_vllm/full_pipeline/train_ranker/evaluate_cassandra parameterised, `demo plan|submit`.
- **UI**: static single-project pages; need dashboard, evidence cards, no-hallucination panel, why-this-rank, graph slice, comparison, token savings, multi-repo pages.
- **Ranker training**: no repo-level split, no LORO, no feature importance export, no overfitting warning, no metadata.
- **No-hallucination**: `files_exist`/`entities_exist` validators exist but have no source index to check against — currently pass trivially.

## Next implementation plan (execution order)

1 gap report ✔ → 2 SQLite → 6 source index → 7 graph slices/cache → multi-repo core (split mgr, repo-independent features, masking) → 8 multi-repo dataset → 9 ranker (LORO, importance, metadata) → 4 RefactoringMiner execute → 5 Arcan/Designite execute → 10 model UX → 13 OpenRewrite validate → 14 Cassandra eval+dry-run → addendum 5 unseen repo → addendum 6 generalisation report → 15 creative (6) → 16 FastAPI → 17 inter-agent docs → 18/19 demos → 11/12 slurm+LoRA → 3 UI upgrade → 20 final verify + docs. Tests at each milestone.
