# Tool Outputs Summary

## Purpose

Compact record of available tool outputs, so Claude does not inspect raw Arcan/Designite logs unless needed.

## Current status

No tool outputs summarized yet.

## Expected evidence sources

- RefactoringMiner JSON output
- Arcan architecture smells
- Designite smells and metrics
- dependency graph edges
- optional JDeps or ArchUnit outputs
- OpenRewrite dry-run/validation logs

## How to update

Run:

```bash
python scripts/summarize_tool_outputs.py --input data/raw --output data/memory/tool_outputs_summary.md
```

## Claude instruction

Before reading raw files under `data/raw/`, inspect this summary and only request exact files/records that are needed.
