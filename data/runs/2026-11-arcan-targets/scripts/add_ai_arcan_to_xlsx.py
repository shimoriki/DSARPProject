"""Write the AI (agentic, ERNIE 5.5 Flash) arm on the beam's Arcan targets into a sheet of
docs/pipeline_comparison_tika.xlsx, next to the beam sheet. Reads agentic/arcan_<repo>/rows.jsonl
(first attempt, repair budget 0) and agentic/arcan_repair_<repo>/rows_repair.jsonl (repair budget 5,
build/test failures only), and pairs each target with the beam's row from beam_arcan/<repo>/rows.jsonl.
Rebuilt on every run; only repos with a summary.json are written."""
import json
import sys
from copy import copy
from pathlib import Path

from openpyxl import load_workbook

S = Path(__file__).parent
XLSX = Path(sys.argv[1])
SHEET, AFTER = "AI arm on Arcan targets", "Beam on Arcan targets"
REPOS = ["apache-pdfbox", "apache-commons-compress", "apache-logging-log4j2"]
PREFIX = {"apache-pdfbox": "org.apache.pdfbox.", "apache-commons-compress": "org.apache.commons.compress.",
          "apache-logging-log4j2": "org.apache.logging.log4j."}
HEAD = ["Repo", "Arm", "Cycle (Arcan cluster)", "Size", "Stage", "Level", "Verdict", "Failed gate",
        "Packages left (Arcan)", "Arcan: target gone", "Moves", "API warning",
        "Beam level", "Beam verdict", "Beam target gone"]


def rows(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def short(name, repo):
    return name[len(PREFIX[repo]):] if name.startswith(PREFIX[repo]) else name


def style(dst, src):
    dst.font, dst.fill, dst.alignment, dst.border = (copy(src.font), copy(src.fill),
                                                     copy(src.alignment), copy(src.border))


wb = load_workbook(XLSX)
if SHEET in wb.sheetnames:
    del wb[SHEET]
ws = wb.create_sheet(SHEET, index=wb.sheetnames.index(AFTER) + 1)
hdr, body = wb["Targets O vs A"]["A1"], wb["Targets O vs A"]["A2"]
for i, h in enumerate(HEAD, 1):
    style(ws.cell(1, i, h), hdr)
row, done = 2, []
for repo in REPOS:
    first = S / "agentic" / ("arcan_" + repo)
    if not (first / "summary.json").exists():
        continue
    done.append(repo)
    beam = {tuple(r["component"]): r for r in rows(S / "beam_arcan" / repo / "rows.jsonl")}
    rep_dir = S / "agentic" / ("arcan_repair_" + repo)
    arms = [("AI (ERNIE)", rows(first / "rows.jsonl"))]
    if (rep_dir / "summary_repair.json").exists():
        arms.append(("AI + repair (budget 5)", rows(rep_dir / "rows_repair.jsonl")))
    for arm, rs in arms:
        for r in rs:
            v = r.get("verdict") or {}
            b = beam.get(tuple(r["component"])) or {}
            bv = b.get("verdict") or {}
            moves = ", ".join("%s -> %s" % (m[0].rsplit(".", 1)[1], short(m[1], repo)) for m in r.get("moves") or [])
            vals = [repo, arm, ", ".join(short(c, repo) for c in r["component"]), r.get("size"), r.get("stage"),
                    str(r.get("level")), v.get("state") or "n/a", v.get("failed_gate"), r.get("measured_left"),
                    "yes" if str(r.get("level")) == "4c" else "no", moves or None,
                    (v.get("warnings") or {}).get("api"),
                    str(b.get("level")) if b else None, (bv.get("state") or "n/a") if b else None,
                    ("yes" if str(b.get("level")) == "4c" else "no") if b else None]
            for i, val in enumerate(vals, 1):
                style(ws.cell(row, i, val), body)
            row += 1
last = row - 1

row += 1
for i, h in enumerate(["Repo", "Arm", "Targets", "PASS", "Arcan target gone (4c)", "PASS and target gone",
                       "Beam: PASS and target gone"], 1):
    style(ws.cell(row, i, h), hdr)
rng = lambda c: "$%s$2:$%s$%d" % (c, c, last)
for repo in done:
    for arm in ("AI (ERNIE)", "AI + repair (budget 5)"):
        row += 1
        k = '%s,"%s",%s,"%s"' % (rng("A"), repo, rng("B"), arm)
        vals = [repo, arm, "=COUNTIFS(%s)" % k, '=COUNTIFS(%s,%s,"PASS")' % (k, rng("G")),
                '=COUNTIFS(%s,%s,"yes")' % (k, rng("J")),
                '=COUNTIFS(%s,%s,"PASS",%s,"yes")' % (k, rng("G"), rng("J")),
                '=COUNTIFS(%s,%s,"PASS",%s,"yes")' % (k, rng("N"), rng("O"))]
        for i, val in enumerate(vals, 1):
            style(ws.cell(row, i, val), body)
row += 2
for note in ["Run: python -m dsarp.agentic.run <beam baseline_tree> <out> --targets-from <beam preregistration.json> "
             "--model baidu/ernie-5.5-flash-preview:free --engine text --facades --rounds 3 --uncapped, frozen "
             "(--freeze then --confirm --repair-budget 0). Same frozen tree, targets and baseline tests as the beam.",
             "Repair arm: --repair-budget 5, rerun only on targets whose first attempt failed at the build or tests.",
             "Beam columns: the beam's result on the same target (sheet 'Beam on Arcan targets').",
             "Log4j2 template.json and test.junit: the AI arm proposed the same moves as the beam but failed the "
             "structural gate with 'a new cycle appeared'. That cycle is the baseline's 49-package core cycle plus "
             "org.apache.logging.log4j.util.internal, which no move touches. Cause: SerializationUtil exists twice "
             "(log4j-api, which depends on util and status, and a log4j-api-java9 stub), and which copy the cycle "
             "oracle (ArchUnit importPaths) keeps depends on the working copy's absolute path. The same class files "
             "give 49 under beam_arcan/.../work/copy and 50 under agentic/.../work/copy. These two FAILs are an "
             "oracle artefact, not a property of the plans.",
             "Struts left out: its baseline test run was partial, so every verdict there is INVALID.",
             "Levels as on the beam sheet: 4c Arcan finds the target cycle gone, 4b shrank, 4a no change, "
             "1 build failed, 0 no plan."]:
    style(ws.cell(row, 1, note), body)
    row += 1
for letter, w in zip("ABCDEFGHIJKLMNO", (24, 22, 60, 6, 9, 7, 9, 12, 12, 10, 70, 30, 10, 11, 12)):
    ws.column_dimensions[letter].width = w
ws.freeze_panes = "A2"
wb.save(XLSX)
print("saved", XLSX, "repos", done, "rows", last - 1)
