# Arcan-target runs and model check, November 2026

Raw outputs behind the "Beam on Arcan targets", "AI arm on Arcan targets",
"Model check" and "How refactoring works" sheets of
`docs/pipeline_comparison_tika.xlsx`.

- `beam_arcan/<repo>/`: the beam's plans (`preregistration.json`) and results
  (`rows.jsonl`, `summary.json`).
- `agentic/arcan_<repo>/`: the AI arm (ERNIE 5.5 Flash), first attempt.
  `arcan_repair_<repo>/` is the repair arm (budget 5).
- `agentic/arc_<model>/<repo>/llm_plans.json`: every model-check round, with
  the model's operations, rationale and the checker's rejections. The
  `arc_<model>.log` file holds the Arcan-verified score.
- `scripts/`: the scripts that wrote the workbook sheets. They expect
  `agentic/` and `beam_arcan/` next to the script, so copy them one level up
  before rerunning.

The repo's .gitignore excludes `*.log` and `*.jsonl`; the files here were
added with `git add -f`.

Not kept: the baseline trees, work copies and Maven test logs (some 3.8 GB
each), and any file over 1 MB. The Log4j2 re-judge
(`arcan_rejudge_apache-logging-log4j2`) was still running when this was copied.
