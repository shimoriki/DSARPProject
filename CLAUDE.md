# CLAUDE.md

Project: DSARP Evidence-Based Refactoring Agent.

Goal: build a modular Java refactoring-suggestion system using:
- RefactoringMiner commit data
- Arcan / Designite smell evidence
- dependency graphs
- candidate generation
- ranking
- local/HPC LLM explanation
- OpenRewrite recipe plans
- human HGRS review

## Token policy

Use tokens carefully.

- Do not read whole repositories unless explicitly asked.
- Do not read full logs, full graphs, full datasets, or large JSONL files.
- First check `data/memory/`, `data/normalized/`, and cached summaries.
- Read only the specific files needed for the current task.
- Prefer evidence IDs, graph slices, and source snippets over full raw files.
- Before changing code, inspect the smallest relevant module.
- After each major task, update `data/memory/current_status.md`.

## No-hallucination policy

- Never invent files, classes, methods, dependency edges, tool findings, commits, or OpenRewrite validation results.
- Every refactoring suggestion must cite evidence IDs.
- If evidence is missing, write `requires_source_inspection`.
- Mark OpenRewrite recipes as `draft` unless dry-run/build/test validation passed.

## Output contract

All generated refactoring suggestions must follow:

```text
/docs/schemas/suggestion_schema.json
```

Every suggestion must include:

```text
evidence_used
unsupported_claims
edge_direction_status
limitations
verification_status
```

## Preferred workflow

```text
read compact project memory
→ inspect relevant evidence case
→ inspect affected graph slice
→ inspect exact source snippet only if needed
→ generate schema-valid output
→ update compact memory summary
```

Do not repeat project background unless requested.
