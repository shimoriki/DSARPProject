# Graph Summary

## Purpose

Compact dependency graph memory for token-efficient agent work.

## Current status

No graph summarized yet.

## Expected contents

- node count
- edge count
- graph level: package/class/module/service
- strongly connected components
- largest cycles
- top fan-in components
- top fan-out components
- central components
- available evidence IDs

## How to update

Run:

```bash
python scripts/summarize_graph.py --input data/graphs --output data/memory/graph_summary.md
```

## Claude instruction

Never load full `.graphml`, `.dot`, or full edge CSV into context unless explicitly required. Use graph slices and evidence IDs.
