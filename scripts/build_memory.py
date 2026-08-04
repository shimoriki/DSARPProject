#!/usr/bin/env python3
"""Build or refresh compact DSARP memory files.

This script intentionally avoids reading huge raw datasets. It creates stable
summary files Claude can inspect before touching raw logs or source trees.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEMORY_DIR = ROOT / "data" / "memory"

TEMPLATES = {
    "current_status.md": """# Current Status

## Last updated

{now}

## Current objective

Build DSARP Evidence-Based Refactoring Agent with token-efficient Claude workflows.

## Completed work

- Memory folder initialized.

## Current code state

To be updated by Claude after each task.

## Next recommended task

Implement foundational schemas and config system.

## Files changed recently

None recorded yet.

## Commands tested

None recorded yet.

## Problems / risks

- Avoid loading large JSONL, raw logs, full dependency graphs, or model files into Claude context.
""",
    "project_summary.md": """# Project Summary

DSARP Evidence-Based Refactoring Agent generates ranked, evidence-based Java refactoring suggestions using RefactoringMiner, Arcan, Designite, dependency graphs, candidate generation, ranking, LLM explanation, OpenRewrite recipe plans, and human HGRS review.
""",
    "architecture_summary.md": """# Architecture Summary

Modular Python monorepo. Raw tool outputs are normalized before being used by agents or models. All major modules communicate through stable schemas.
""",
    "tool_outputs_summary.md": """# Tool Outputs Summary

No tool outputs summarized yet. Run `python scripts/summarize_tool_outputs.py` after importing tool outputs.
""",
    "graph_summary.md": """# Graph Summary

No graph summarized yet. Run `python scripts/summarize_graph.py` after building dependency graphs.
""",
    "refactoringminer_summary.md": """# RefactoringMiner Summary

No RefactoringMiner events summarized yet. Run `python scripts/summarize_refactoringminer.py` after mining refactorings.
""",
    "openrewrite_capability_summary.md": """# OpenRewrite Capability Summary

OpenRewrite recipes are drafts unless dry run/build/tests/graph re-analysis validate them. Design-heavy refactorings should produce recipe plans, not false automation claims.
""",
}


def main() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    for name, template in TEMPLATES.items():
        path = MEMORY_DIR / name
        if not path.exists():
            path.write_text(template.format(now=now), encoding="utf-8")
            print(f"created {path}")
        else:
            print(f"exists  {path}")

    print("\nMemory files are ready. Ask Claude to read data/memory/current_status.md first.")


if __name__ == "__main__":
    main()
