#!/usr/bin/env python3
"""Summarize dependency graph files into compact graph memory."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


def summarize_edge_csv(path: Path) -> dict:
    rows = 0
    sources = Counter()
    targets = Counter()
    headers = []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        source_key = next((k for k in headers if k.lower() in {"source", "src", "from", "from_component"}), None)
        target_key = next((k for k in headers if k.lower() in {"target", "dst", "to", "to_component"}), None)
        for row in reader:
            rows += 1
            if source_key:
                sources[row.get(source_key, "")] += 1
            if target_key:
                targets[row.get(target_key, "")] += 1
    return {
        "rows": rows,
        "headers": headers,
        "top_fan_out": sources.most_common(20),
        "top_fan_in": targets.most_common(20),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/graphs", help="Graph folder or edge CSV")
    parser.add_argument("--output", default="data/memory/graph_summary.md")
    args = parser.parse_args()

    inp = Path(args.input)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    files = [inp] if inp.is_file() else list(inp.rglob("*.csv")) if inp.exists() else []
    lines = ["# Graph Summary", "", f"Input: `{inp}`", f"CSV graph files found: {len(files)}", ""]

    for path in files[:50]:
        lines.append(f"## `{path.as_posix()}`")
        try:
            summary = summarize_edge_csv(path)
            lines.append(f"Edges/rows: {summary['rows']}")
            lines.append(f"Headers: {summary['headers'][:30]}")
            lines.append("")
            lines.append("Top fan-out:")
            for node, count in summary["top_fan_out"][:10]:
                lines.append(f"- `{node}`: {count}")
            lines.append("")
            lines.append("Top fan-in:")
            for node, count in summary["top_fan_in"][:10]:
                lines.append(f"- `{node}`: {count}")
        except Exception as exc:
            lines.append(f"Error summarizing file: {exc}")
        lines.append("")

    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
