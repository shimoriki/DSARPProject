# Architecture Summary

## System style

Modular Python monorepo with separate packages for:

- repository management,
- RefactoringMiner mining,
- Arcan and Designite adapters,
- dependency graph building,
- evidence normalization,
- candidate generation,
- ranking,
- local/HPC model providers,
- OpenRewrite recipe generation,
- validators,
- Streamlit UI,
- Slurm/HPC execution.

## Key principle

Every module communicates through stable schemas. Raw tool outputs are imported and normalized before reaching an agent or model.

## Main modules

```text
core/repositories
core/refactoring_miner
core/tools
core/graphs
core/evidence
core/alignment
core/candidates
core/ranking
core/models
core/agents
core/openrewrite
core/validation
core/evaluation
ui/
scripts/
slurm/
```

## Stable schemas

- `docs/schemas/suggestion_schema.json`
- `docs/schemas/context_package_schema.json`
- `docs/schemas/hgrs_review_schema.json`

## Token rule

Claude should inspect this summary before reading architecture files or source modules.
