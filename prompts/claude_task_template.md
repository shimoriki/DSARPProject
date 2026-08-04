# Claude Token-Efficient Task Template

You must work token-efficiently.

Before reading files:
1. Read `CLAUDE.md`.
2. Read `data/memory/current_status.md` if it exists.
3. Inspect only files directly needed for this task.

Do not load:
- large datasets,
- raw tool logs,
- full dependency graphs,
- model files,
- training JSONL files,
- entire repository source trees.

Use file paths instead of injecting whole files.
When evidence is needed, prefer normalized evidence summaries and evidence IDs.

## Task

[WRITE ONE SMALL TASK HERE]

## Allowed files

- [path/to/file1]
- [path/to/file2]

## Do not read

- `data/training/`
- `data/raw/`
- `outputs/`
- `models/`
- `logs/`
- any `*.jsonl`, `*.log`, `*.graphml`, or `*.dot` unless explicitly allowed

## Output required

After completing the task, report:

1. files changed,
2. short explanation of changes,
3. commands to test,
4. problems found,
5. next recommended step.

Then update `data/memory/current_status.md` with a compact summary. Do not include long code blocks in the memory file.
