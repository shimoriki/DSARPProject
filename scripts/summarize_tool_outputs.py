#!/usr/bin/env python3
"""Summarize raw tool output folders without sending full logs to Claude."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Iterable

TEXT_EXTS = {".txt", ".log", ".csv", ".json", ".xml"}


def iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return (p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_EXTS)


def summarize_csv(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
            reader = csv.DictReader(f)
            rows = 0
            headers = reader.fieldnames or []
            smell_counter = Counter()
            for row in reader:
                rows += 1
                for key in ("Smell", "smell", "Smell Type", "smell_type", "Type", "type"):
                    if key in row and row[key]:
                        smell_counter[row[key]] += 1
                        break
        return {"rows": rows, "headers": headers[:30], "smell_counts": dict(smell_counter.most_common(20))}
    except Exception as exc:
        return {"error": str(exc)}


def summarize_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        if isinstance(data, list):
            return {"type": "list", "items": len(data), "sample_keys": list(data[0].keys())[:20] if data and isinstance(data[0], dict) else []}
        if isinstance(data, dict):
            return {"type": "object", "keys": list(data.keys())[:40]}
        return {"type": type(data).__name__}
    except Exception as exc:
        return {"error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/raw", help="Raw tool output folder")
    parser.add_argument("--output", default="data/memory/tool_outputs_summary.md")
    args = parser.parse_args()

    root = Path(args.input)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    files = list(iter_files(root))
    lines = ["# Tool Outputs Summary", "", f"Input folder: `{root}`", f"Files found: {len(files)}", ""]

    for path in files[:200]:
        rel = path.as_posix()
        size_mb = path.stat().st_size / (1024 * 1024)
        lines.append(f"## `{rel}`")
        lines.append(f"Size: {size_mb:.2f} MB")
        if path.suffix.lower() == ".csv":
            summary = summarize_csv(path)
            lines.append("```json")
            lines.append(json.dumps(summary, indent=2)[:4000])
            lines.append("```")
        elif path.suffix.lower() == ".json":
            summary = summarize_json(path)
            lines.append("```json")
            lines.append(json.dumps(summary, indent=2)[:4000])
            lines.append("```")
        else:
            preview = path.read_text(encoding="utf-8", errors="ignore")[:1200]
            lines.append("Preview:")
            lines.append("```text")
            lines.append(preview)
            lines.append("```")
        lines.append("")

    if len(files) > 200:
        lines.append(f"Skipped {len(files) - 200} additional files. Summarize specific folders separately if needed.")

    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
