# Token Optimisation Guide for Claude in DSARP

## Principle

Claude should operate on compact memory files, stable schemas, and exact target files, not raw datasets or entire repositories.

## Context levels

```text
Level 0: stable instructions
Level 1: project memory summaries
Level 2: evidence slice for the current smell/candidate
Level 3: raw detail only on demand
```

Claude should usually receive Level 0 + Level 1 + a small Level 2 slice.

## What to avoid

Do not paste or inject:

```text
large JSONL datasets
full Designite logs
full Arcan outputs
full dependency graphs
large RefactoringMiner outputs
whole source repositories
model files
```

## Best workflow

```text
read CLAUDE.md
read data/memory/current_status.md
read the relevant summary
inspect only the exact target file
make the change
run a small test
update current_status.md
```

## Good Claude request

```text
Task: implement only the Pydantic suggestion schema.
Allowed files: core/schemas/suggestion.py, docs/schemas/suggestion_schema.json.
Do not read data/raw, data/training, outputs, models, logs, or repository source trees.
Update data/memory/current_status.md after changes.
```

## Bad Claude request

```text
Read the whole repo and build everything.
```
