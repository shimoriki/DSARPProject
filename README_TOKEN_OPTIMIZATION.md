# DSARP Claude Token Optimisation Pack

Copy these files into the root of your DSARP repository.

## What this pack gives you

- `CLAUDE.md`: stable Claude Code project instructions.
- `data/memory/*.md`: compact memory files Claude should read before raw files.
- `docs/schemas/*.json`: stable schemas for suggestions, context packages, and HGRS review records.
- `prompts/claude_task_template.md`: reusable prompt template for small, token-bounded Claude tasks.
- `scripts/build_memory.py`: creates compact project memory from existing summaries.
- `scripts/summarize_tool_outputs.py`: summarizes Arcan/Designite-style exports without loading huge raw logs into Claude.
- `scripts/summarize_graph.py`: summarizes dependency graphs into graph metrics and top components.
- `scripts/summarize_refactoringminer.py`: summarizes RefactoringMiner JSON output.
- `.gitignore.dsarp_append`: rules to paste into your `.gitignore`.

## Install

From your repo root:

```bash
unzip DSARP_Claude_Token_Optimization_Pack.zip
```

Then append the ignore rules:

```bash
cat .gitignore.dsarp_append >> .gitignore
```

On Windows PowerShell:

```powershell
Get-Content .gitignore.dsarp_append | Add-Content .gitignore
```

## First commands to run

```bash
python scripts/build_memory.py
```

Then in Claude Code start with:

```text
Read CLAUDE.md and data/memory/current_status.md first. Do not inspect raw datasets unless needed.
```

## Main rule

Claude should work from:

```text
schemas + memory summaries + exact target files
```

not from:

```text
whole repo + full datasets + logs + full graphs
```
