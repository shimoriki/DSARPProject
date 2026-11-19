"""Add the OpenRouter runs (Tika agentic arm for Nemotron Ultra and Ling Flash, and the
Arcan-verified model check) to docs/pipeline_comparison_tika.xlsx. Values come from the run
folders in this scratchpad; nothing is typed by hand except the model-check scores read from
the smoke logs."""
import json
import sys
from copy import copy
from pathlib import Path

from openpyxl import load_workbook

S = Path(__file__).parent
XLSX = Path(sys.argv[1])
ARMS = [("N", "nvidia_nemotron-3-ultra-550b-a55b_free", "Nemotron Ultra 550B"),
        ("L", "inclusionai_ling-3_2-flash_free", "Ling 3.2 Flash")]
FIELDS = ["stage", "level", "verdict", "failed gate", "packages left", "moves", "API", "secs",
          "repair (budget 5)"]


def rows(path):
    return {tuple(json.loads(l)["component"]): json.loads(l)
            for l in path.read_text(encoding="utf-8").splitlines() if l.strip()}


def repair_text(r):
    if not r:
        return "not needed"
    v = r.get("verdict") or {}
    b = (r.get("repair") or {}).get("build") or {}
    t = (r.get("repair") or {}).get("tests") or {}
    parts = []
    if b:
        parts.append("build: %d rounds, %d files edited, ok=%s" % (
            len(b.get("rounds") or []), len(b.get("edited") or []), b.get("ok")))
    if t:
        parts.append("tests: %d rounds, ok=%s" % (len(t.get("rounds") or []), t.get("ok")))
    parts.append("then %s%s, %s packages left" % (
        v.get("state"), (" at " + v["failed_gate"]) if v.get("failed_gate") else "",
        r.get("measured_left")))
    return "; ".join(parts)


def cells(r, rep):
    v = r.get("verdict") or {}
    api = (v.get("warnings") or {}).get("api")
    return [r.get("stage"), str(r.get("level")), v.get("state") or 0, v.get("failed_gate"),
            r.get("measured_left"), ", ".join(m[0].rsplit(".", 1)[1] for m in r.get("moves") or []) or None,
            api, r.get("secs"), repair_text(rep)]


def style(dst, src):
    dst.font, dst.fill, dst.alignment, dst.border = (copy(src.font), copy(src.fill),
                                                     copy(src.alignment), copy(src.border))


wb = load_workbook(XLSX)

# Targets O vs A: one block of columns per arm, rows matched by the cycle's packages.
ws = wb["Targets O vs A"]
col = ws.max_column + 1
for key, tag, name in ARMS:
    base = rows(S / ("tika_" + tag) / "rows.jsonl")
    rep = rows(S / ("tika_repair_" + tag) / "rows_repair.jsonl")
    for i, f in enumerate(FIELDS):
        c = ws.cell(1, col + i, "%s %s (%s)" % (key, f, name) if i == 0 else "%s %s" % (key, f))
        style(c, ws["R1"])
        ws.column_dimensions[c.column_letter].width = 30 if f in ("moves", "repair (budget 5)", "API") else 14
    for row in range(2, ws.max_row + 1):
        label = ws.cell(row, 1).value
        comp = tuple(sorted("org.apache.tika." + p.strip() for p in label.split(",")))
        hit = [k for k in base if tuple(sorted(k)) == comp]
        if not hit:
            raise SystemExit("no %s row for %s" % (key, label))
        for i, v in enumerate(cells(base[hit[0]], rep.get(hit[0]))):
            style(ws.cell(row, col + i, v), ws.cell(row, 18))
    col += len(FIELDS)

# Model check: hosted models under the Ollama table, scored by Arcan (smoke rerun, 4a2a90a).
mc = wb["Model check"]
start = mc.max_row + 2
heads = ["OpenRouter free model (hosted)", "Cycles dissolved, Arcan-verified", "Cases", "Bar", "Result",
         "Earlier run (graph + dry run, Arcan recheck)", "Notes"]
for i, h in enumerate(heads, 1):
    style(mc.cell(start, i, h), mc["A1"])
for letter, w in (("F", 22), ("G", 60)):
    mc.column_dimensions[letter].width = w
CAP = "daily cap: 50 requests/day per key, reset over max_wait; queued after the reset"
data = [("nvidia/nemotron-3-ultra-550b-a55b:free", 1, "2 of 3 (Arcan agrees on both)",
         "text dissolved; exec and math: no plan in 3 rounds"),
        ("inclusionai/ling-3.2-flash:free", 1, "2 of 3 (Arcan agrees on both)",
         "text dissolved; exec and math: no plan in 3 rounds"),
        ("cohere/north-mini-code:free", None, "0 of 3", "exec: no plan in 3 rounds; math, text: " + CAP),
        ("nvidia/nemotron-3.5-super-vl:free", None, "0 of 3 (invalid: resets, timeout)", CAP),
        ("baidu/ernie-5.5-flash-preview:free", None, "0 of 3 (invalid: daily cap)", CAP),
        ("google/gemma-4-26b-a4b-it:free", None, "0 of 3 (invalid: daily cap)", CAP),
        ("google/gemma-4-31b-it:free", None, "0 of 3 (invalid: upstream 429)", CAP)]
for j, (m, passed, earlier, note) in enumerate(data, start + 1):
    vals = [m, passed, 3, 2, '=IF(B{0}="","NOT MEASURED",IF(B{0}>=D{0},"PASS","FAIL"))'.format(j), earlier, note]
    for i, v in enumerate(vals, 1):
        style(mc.cell(j, i, v), mc["B2"])

# Summary: accepted targets per arm, counted from the Targets sheet, plus a note.
sm = wb["Summary"]
r0 = sm.max_row + 2
verdict_col = {"O": "E", "A": "L"}
for k, (key, _, _) in enumerate(ARMS):
    verdict_col[key] = ws.cell(1, 19 + k * len(FIELDS) + 2).column_letter
style(sm.cell(r0, 1, "Agentic arms on the same 5 Tika targets (Targets O vs A sheet)"), sm["A1"])
for i, (key, name) in enumerate([("O", "O our beam"), ("A", "A qwen2.5-coder:7b"),
                                 ("N", "N Nemotron Ultra 550B"), ("L", "L Ling 3.2 Flash")], 2):
    style(sm.cell(r0, i, name), sm["A1"])
    style(sm.cell(r0 + 1, i, "=COUNTIF('Targets O vs A'!$%s$2:$%s$6,\"PASS\")" % (verdict_col[key], verdict_col[key])),
          sm["B2"])
style(sm.cell(r0 + 1, 1, "Targets accepted by every gate (verdict PASS), of 5"), sm["A2"])
sm.column_dimensions["E"].width = sm.column_dimensions["D"].width
style(sm.cell(r0 + 3, 1, "N and L: OpenRouter free models, run like A (engine text, facades on, 3 rounds, frozen "
                         "plans, then a repair arm with budget 5 on targets that failed build or tests). They have "
                         "no rows in Patches. L's one PASS (geo.topic, level 4c) is the same GeoParserConfig move the "
                         "beam made; N proposed that move too, but its test run stopped part way (INVALID)."),
      sm["A20"])

wb.save(XLSX)
print("saved", XLSX, "verdict columns", verdict_col)
