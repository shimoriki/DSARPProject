# RefactoringMiner Summary

## Purpose

Compact summary of historical refactoring events mined from repositories.

## Current status

No RefactoringMiner events summarized yet.

## Expected contents

- repositories mined
- commits analysed
- refactoring events detected
- refactoring type distribution
- failed commits
- top affected packages/classes
- sample events by type

## How to update

Run:

```bash
python scripts/summarize_refactoringminer.py --input data/refactoring_events --output data/memory/refactoringminer_summary.md
```

## Claude instruction

Do not load full RefactoringMiner JSON files or huge JSONL training datasets. Use this summary first.
