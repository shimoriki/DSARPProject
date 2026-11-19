"""Write the Arcan-targeted beam runs (beam_arcan/<repo>/rows.jsonl) into a sheet of
docs/pipeline_comparison_tika.xlsx. The sheet is rebuilt on every run, so rerunning after
more repos finish adds them. Only repos with a rows.jsonl are written; nothing is typed by hand."""
import ast
import json
import re
import sys
from copy import copy
from pathlib import Path

from openpyxl import load_workbook

S = Path(__file__).parent / "beam_arcan"
XLSX = Path(sys.argv[1])
SHEET = "Beam on Arcan targets"
REPOS = ["apache-pdfbox", "apache-commons-compress", "apache-struts", "apache-logging-log4j2"]
PREFIX = {"apache-pdfbox": "org.apache.pdfbox.", "apache-commons-compress": "org.apache.commons.compress.",
          "apache-struts": "org.apache.struts2.", "apache-logging-log4j2": "org.apache.logging.log4j."}
HEAD = ["Repo", "Baseline tests", "Cycle (Arcan cluster)", "Size", "Stage", "Level", "Verdict",
        "Failed gate", "Predicted left", "Packages left (Arcan)", "Arcan: target gone", "Moves",
        "API warning", "Why (first line)"]


def style(dst, src):
    dst.font, dst.fill, dst.alignment, dst.border = (copy(src.font), copy(src.fill),
                                                     copy(src.alignment), copy(src.border))


def baseline(repo):
    p = S / repo / "freeze.log"
    m = p.exists() and re.search(r"baseline tests: (\{.*\})", p.read_text(encoding="utf-8", errors="replace"))
    if not m:
        return None
    b = ast.literal_eval(m.group(1))
    frozen = (S / repo / "preregistration.json").exists()
    return "%d run, %d failed%s%s" % (b["tests_run"], b["failures"] + b["errors"],
                                     ", partial" if b["partial"] else "", "" if frozen else " (not frozen)")


def short(name, repo):
    return name[len(PREFIX[repo]):] if name.startswith(PREFIX[repo]) else name


wb = load_workbook(XLSX)
if SHEET in wb.sheetnames:
    del wb[SHEET]
ws = wb.create_sheet(SHEET, index=wb.sheetnames.index("Model check"))
hdr, body = wb["Targets O vs A"]["A1"], wb["Targets O vs A"]["A2"]
for i, h in enumerate(HEAD, 1):
    style(ws.cell(1, i, h), hdr)
row, done = 2, []
for repo in REPOS:
    p = S / repo / "rows.jsonl"
    if not (S / repo / "summary.json").exists():   # still running or not started
        continue
    done.append(repo)
    base = baseline(repo)
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        v = r.get("verdict") or {}
        moves = ", ".join("%s -> %s" % (m[0].rsplit(".", 1)[1], short(m[1], repo)) for m in r.get("moves") or [])
        why = (r.get("why") or "").splitlines()
        vals = [repo, base, ", ".join(short(c, repo) for c in r["component"]), r.get("size"), r.get("stage"),
                str(r.get("level")), v.get("state") or "n/a", v.get("failed_gate"), r.get("predicted_left"),
                r.get("measured_left"), "yes" if str(r.get("level")) == "4c" else "no", moves or None,
                (v.get("warnings") or {}).get("api"), why[0][:300] if why else None]
        for i, val in enumerate(vals, 1):
            style(ws.cell(row, i, val), body)
        row += 1
last = row - 1

# Per-repo counts, as formulas over the rows above.
row += 1
for i, h in enumerate(["Repo", "Targets", "Accepted by every gate (PASS)", "Arcan target gone (4c)",
                       "PASS and target gone"], 1):
    style(ws.cell(row, i, h), hdr)
for repo in done:
    row += 1
    rng = lambda c: "$%s$2:$%s$%d" % (c, c, last)
    vals = [repo, '=COUNTIF(%s,"%s")' % (rng("A"), repo),
            '=COUNTIFS(%s,"%s",%s,"PASS")' % (rng("A"), repo, rng("G")),
            '=COUNTIFS(%s,"%s",%s,"yes")' % (rng("A"), repo, rng("K")),
            '=COUNTIFS(%s,"%s",%s,"PASS",%s,"yes")' % (rng("A"), repo, rng("G"), rng("K"))]
    for i, val in enumerate(vals, 1):
        style(ws.cell(row, i, val), body)
row += 2
for note in ["Run: python -m dsarp.experiments.scc_dissolve <repo> --arcan-targets --engine text --facades "
             "--max-size 15 --limit 10, frozen (--freeze then --confirm) when the baseline test run was complete.",
             "Targets are Arcan's own package-cycle clusters. Level 4c: an Arcan run after the change finds no "
             "cycle holding 2 or more of the target's packages. 4b: the cycle shrank but is still there. "
             "4a: no change Arcan can see. 1: build failed. 0: no plan.",
             "API warning: japicmp found public types moved."]:
    style(ws.cell(row, 1, note), body)
    row += 1
for letter, w in zip("ABCDEFGHIJKLMN", (24, 26, 60, 6, 9, 7, 9, 12, 9, 12, 10, 70, 30, 60)):
    ws.column_dimensions[letter].width = w
ws.freeze_panes = "A2"
wb.save(XLSX)
print("saved", XLSX, "repos", done, "rows", last - 1)
