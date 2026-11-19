"""Write an "Example records" sheet into the comparison workbook: one real record of each kind kept in
data/runs/2026-11-arcan-targets, field by field, with what the field means. Values are read from the
files, not typed in. Usage: py add_examples_to_xlsx.py <workbook.xlsx> <runs dir>"""
import json
import sys
from copy import copy
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font

XLSX, RUNS = sys.argv[1], Path(sys.argv[2])
SHEET, AFTER = "Example records", "How refactoring works"
L4J = "org.apache.logging.log4j."


def jl(p):
    return [json.loads(l) for l in (RUNS / p).read_text(encoding="utf-8").splitlines() if l.strip()]


def junit(rs):
    return next(r for r in rs if any(c.endswith("test.junit") for c in r["component"]))


def short(s):
    return s.replace(L4J, "").replace("org.apache.commons.text.", "")


def moves(ms):
    return "; ".join("%s -> %s" % (short(a), short(b)) for a, b in ms) or "none"


pre = junit(json.loads((RUNS / "beam_arcan/apache-logging-log4j2/preregistration.json").read_text(encoding="utf-8"))["plans"])
beam = junit(jl("beam_arcan/apache-logging-log4j2/rows.jsonl"))
ai = junit(jl("agentic/arcan_apache-logging-log4j2/rows.jsonl"))
summ = json.loads((RUNS / "beam_arcan/apache-logging-log4j2/summary.json").read_text(encoding="utf-8"))
mc = json.loads((RUNS / "agentic/arc_baidu_ernie-5_5-flash-preview_free/apache-commons-text/llm_plans.json").read_text(encoding="utf-8"))[0]


def row_fields(r):
    t, v, api = r.get("tests") or {}, r["verdict"], r.get("api") or {}
    return [
        ("moves", moves(r["moves"]), "The class moved and where to."),
        ("changed_files", r.get("changed_files"), "Java files edited (the moved file plus every import that named it)."),
        ("facades", ", ".join("%s (%s)" % (short(f["type"]), f["kind"]) for f in r.get("facades") or []) or "none",
         "Stand-in left at the old name so outside code keeps compiling."),
        ("compile", r.get("compile"), "Did the whole project still build?"),
        ("measured_left", r.get("measured_left"), "Packages still in the cycle after the move, measured on the built code."),
        ("novel_cycles", "%d new cycle(s)" % len(r.get("novel_cycles") or []), "Cycles that were not there before (must be 0)."),
        ("arcan_target_gone", r.get("arcan_target_gone"), "Arcan, run again, no longer reports this cycle."),
        ("api.count", api.get("count"), "Binary-incompatible API changes found by japicmp (reported, not a fail)."),
        ("tests", "%s run, %s failures, %s errors" % (t.get("tests_run"), t.get("failures"), t.get("errors"))
         if t.get("tests_run") is not None else "not run (an earlier gate failed)",
         "Full test suite. Log4j2 already has failures before any change; only new ones count."),
        ("verdict", "%s%s" % (v["state"], " (gate: %s, %s)" % (v["failed_gate"], v["why"]) if v.get("failed_gate") else ""),
         "PASS only if every gate holds."),
        ("level", r.get("level"), "4c target gone, 4b shrank, 4a no change, 2 structural fail, 1 build fail, 0 no plan."),
    ]


EXAMPLES = [
    ("A. A plan before anything is run (beam_arcan/apache-logging-log4j2/preregistration.json)",
     "The beam writes its plan down first, so the result cannot change the plan afterwards.", [
         ("component", ", ".join(short(c) for c in pre["component"]), "The cycle: these packages depend on each other."),
         ("candidates", pre.get("candidates"), "Single-class moves the search looked at."),
         ("moves", moves(pre["moves"]), "The move it chose."),
         ("predicted_left", pre["predicted_left"], "Packages the graph simulation says stay in the cycle (0 = dissolved)."),
     ]),
    ("B. The beam's result for that plan (beam_arcan/apache-logging-log4j2/rows.jsonl)",
     "One line per target, written after the move was applied and every check ran.", row_fields(beam)),
    ("C. The AI arm's result for the same cycle (agentic/arcan_apache-logging-log4j2/rows.jsonl)",
     "ERNIE proposed the same move. The structural FAIL came from the cycle checker's duplicate-class bug "
     "(fixed in 3c042e2); a re-judge is running.", row_fields(ai)),
    ("D. One AI model's rounds (agentic/arc_baidu_ernie-5_5-flash-preview_free/apache-commons-text/llm_plans.json)",
     "Every round of what the model proposed and what the checker said.",
     [("round %d" % (i + 1),
       "; ".join("%s %s -> %s" % (o.get("op"), short(o.get("class") or o.get("impl") or ""),
                                  short(o.get("to") or o.get("consumer") or ""))
                 for o in (json.loads(r["text"])["operations"] if r["text"].strip() else [])) or "empty answer",
       ("refused: " + "; ".join(x[1] for x in r["rejected"])) if r.get("rejected")
       else "nothing to check" if not r["text"].strip()
       else "accepted, %s package(s) left in the prediction" % r.get("predicted_left"))
      for i, r in enumerate(mc["rounds"])]),
    ("E. A run summary (beam_arcan/apache-logging-log4j2/summary.json)",
     "Counts over all targets of one repo.", [
         ("targets", summ["targets"], "Cycles attempted."),
         ("levels", ", ".join("%s: %s" % kv for kv in summ["levels"].items()), "How many targets reached each level."),
         ("dissolved", summ["dissolved"], "Targets Arcan no longer reports."),
         ("success", summ["success"], "Targets that passed every gate."),
         ("success_without_api_break", summ["success_without_api_break"], "Passed with zero API breaks."),
     ]),
]

wb = load_workbook(XLSX)
if SHEET in wb.sheetnames:
    del wb[SHEET]
ws = wb.create_sheet(SHEET, index=wb.sheetnames.index(AFTER) + 1)
hdr, body = wb["Targets O vs A"]["A1"], wb["Targets O vs A"]["A2"]
wrap = Alignment(wrap_text=True, vertical="top")


def put(r, c, v, src, bold=False, size=None):
    cell = ws.cell(r, c, v if not isinstance(v, bool) else str(v))
    cell.font, cell.fill, cell.border = copy(src.font), copy(src.fill), copy(src.border)
    if bold or size:
        cell.font = Font(name=src.font.name, bold=True, size=size or src.font.size)
    cell.alignment = wrap


put(1, 1, "Example records: one real record of each kind, field by field", body, size=14)
put(2, 1, "Files are in data/runs/2026-11-arcan-targets in the repo. Values below are read from them.", body)
ws.merge_cells("A2:C2")
r = 4
for title, note, fields in EXAMPLES:
    put(r, 1, title, body, bold=True, size=12)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
    put(r + 1, 1, note, body)
    ws.merge_cells(start_row=r + 1, start_column=1, end_row=r + 1, end_column=3)
    for i, h in enumerate(["Field", "Value", "What it means"], 1):
        put(r + 2, i, h, hdr)
    r += 3
    for f in fields:
        for i, v in enumerate(f, 1):
            put(r, i, v, body)
        r += 1
    r += 1
for letter, w in zip("ABC", (22, 70, 70)):
    ws.column_dimensions[letter].width = w
wb.save(XLSX)
print("saved", XLSX, "rows", r)
