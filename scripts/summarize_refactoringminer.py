#!/usr/bin/env python3
"""Summarize RefactoringMiner JSON outputs for Claude-friendly memory."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8", errors="ignore"))


def event_type(event: dict) -> str:
    return str(event.get("type") or event.get("refactoring_type") or event.get("refactoringType") or "Unknown")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/refactoring_events", help="RefactoringMiner output folder or file")
    parser.add_argument("--output", default="data/memory/refactoringminer_summary.md")
    args = parser.parse_args()

    inp = Path(args.input)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    files = [inp] if inp.is_file() else list(inp.rglob("*.json")) if inp.exists() else []
    type_counts = Counter()
    total_commits = 0
    total_events = 0
    samples = []

    for path in files[:200]:
        try:
            data = load_json(path)
            commits = data.get("commits", []) if isinstance(data, dict) else []
            total_commits += len(commits)
            for commit in commits:
                refs = commit.get("refactorings", []) or []
                total_events += len(refs)
                for ref in refs:
                    typ = event_type(ref)
                    type_counts[typ] += 1
                    if len(samples) < 20:
                        samples.append({
                            "file": path.as_posix(),
                            "commit": commit.get("sha1") or commit.get("commitId") or commit.get("commit"),
                            "type": typ,
                            "description": str(ref.get("description", ""))[:300],
                        })
        except Exception as exc:
            samples.append({"file": path.as_posix(), "error": str(exc)})

    lines = [
        "# RefactoringMiner Summary",
        "",
        f"Input: `{inp}`",
        f"JSON files found: {len(files)}",
        f"Commits summarized: {total_commits}",
        f"Refactoring events summarized: {total_events}",
        "",
        "## Refactoring type distribution",
    ]

    for typ, count in type_counts.most_common(50):
        lines.append(f"- {typ}: {count}")

    lines.extend(["", "## Samples", "", "```json", json.dumps(samples, indent=2), "```"])

    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
