"""Write a plain-language sheet "How refactoring works" into the comparison workbook: what a cycle is,
the steps from finding to checking, and what ERNIE, Cohere and Nemotron Super VL proposed on the
model-check cases (from agentic/arc_<model>/<repo>/llm_plans.json and the model-check logs)."""
import sys
from copy import copy

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font

XLSX = sys.argv[1]
SHEET, AFTER = "How refactoring works", "Model check"

PARTS = [
    ("title", "How the automatic refactoring works, in plain words"),
    ("head", "1. The problem we fix: a package cycle"),
    ("text", "Java code is grouped into packages, like folders. Package A 'depends on' package B when code "
             "in A uses a class from B. If A uses B and B also uses A, the two are tangled in a cycle: "
             "neither can be understood, tested or reused without the other. Arcan, an architecture checker, "
             "finds these cycles."),
    ("text", "Example (Apache Commons Text): package text uses package lookup (StringSubstitutor uses the "
             "lookup classes), and lookup uses text, because lookup code calls StringEscapeUtils, a class "
             "that lives in text (its other imports of text serve only documentation links). Arrows both "
             "ways, so text and lookup form a cycle."),
    ("head", "2. The fix: move one class so the arrows point one way only"),
    ("text", "If StringEscapeUtils moves from text into lookup, lookup no longer needs anything from text. "
             "Now only text uses lookup. The arrows point one way and the cycle is gone. The code itself does "
             "the same thing as before; only where the class lives has changed."),
    ("text", "The other tool is 'invert an edge': put an interface between the two packages so the "
             "dependency goes the other way. The checker allows it only when it is safe (for example, not on "
             "a utility class full of static methods, and not if the class is already an interface)."),
    ("head", "3. The steps, every time"),
    ("step", "Find", "Arcan lists the cycles in the project."),
    ("step", "Plan", "A planner proposes moves: either our search (the 'beam') or an AI model given the "
                     "dependency graph of the cycle."),
    ("step", "Check the plan", "Rules refuse unsafe moves, e.g. a move into another source folder, or a class "
                               "whose package-private parts are used from its old package."),
    ("step", "Predict", "We replay the moves on the dependency graph and count what is left of the cycle. "
                        "If something is left, the AI gets that feedback and tries again (up to 3 rounds)."),
    ("step", "Apply", "The tool moves the file, changes its package line and fixes every import in the "
                      "project. It can leave a small stand-in at the old name so outside code keeps compiling."),
    ("step", "Verify", "The project must still build, the tests must not get worse, no new cycle may appear, "
                       "and Arcan, run again, must no longer report the cycle. API changes are reported "
                       "(japicmp)."),
    ("head", "4. What the three AI models proposed (model check: Commons Exec, Math, Text)"),
    ("table", ["Model", "Project", "Round by round", "Outcome (Arcan rerun)"]),
    ("row", ["ERNIE 5.5 Flash", "Commons Text",
             "1: invert the edge to StringEscapeUtils, refused (utility class: 45 static methods). "
             "2: empty answer. 3: move StringEscapeUtils into lookup.",
             "Cycle gone"]),
    ("row", ["ERNIE 5.5 Flash", "Commons Math",
             "1: invert the edge to VectorialCovariance, refused (it is constructed directly by descriptive). "
             "2: move VectorialCovariance into descriptive.",
             "Cycle gone"]),
    ("row", ["ERNIE 5.5 Flash", "Commons Exec",
             "1 and 3: move DefaultExecutor (and DaemonExecutor) into launcher, refused by the move rules. "
             "2: invert CommandLauncher, refused (already an interface; different source folders).",
             "No valid plan"]),
    ("row", ["Cohere North Mini Code", "Commons Math",
             "1 and 2: move MultivariateSummaryStatistics into moment, still 2 packages tangled. "
             "3: move VectorialCovariance into descriptive.",
             "Cycle gone"]),
    ("row", ["Cohere North Mini Code", "Commons Text",
             "1 and 2: move StrLookup and StringSubstitutor into lookup. 3: move StringLookup and "
             "StringLookupFactory into text. Each still leaves the cycle in the prediction.",
             "Build fine, but Arcan still reports the cycle"]),
    ("row", ["Cohere North Mini Code", "Commons Exec",
             "Moves of DefaultExecutor, CommandLauncherImpl, Java13CommandLauncher refused by the move "
             "rules; inverting CommandLauncher refused.",
             "No valid plan"]),
    ("row", ["Nemotron 3.5 Super VL", "Commons Text",
             "1: move StringEscapeUtils into lookup (right on the first try).",
             "Cycle gone"]),
    ("row", ["Nemotron 3.5 Super VL", "Commons Math",
             "1 and 3: invert the edge to VectorialCovariance, refused. 2: move MultivariateSummaryStatistics "
             "into moment, cycle left.",
             "No working plan in 3 rounds"]),
    ("row", ["Nemotron 3.5 Super VL", "Commons Exec",
             "Moves of DefaultExecutor, CommandLauncher, CommandLauncherFactory refused; inversion refused.",
             "No valid plan"]),
    ("head", "5. In one line"),
    ("text", "ERNIE removed 2 of 3 cycles, Cohere 1, Nemotron Super VL 1. All three found the same small fix "
             "(move one class) when they found one. None solved Commons Exec, because every move they tried "
             "broke a safety rule. The AI only suggests; the checks decide."),
    ("text", "Source: agentic/arc_<model>/<project>/llm_plans.json and arc_<model>.log in the run folder; "
             "scores as on the Model check sheet."),
]

wb = load_workbook(XLSX)
if SHEET in wb.sheetnames:
    del wb[SHEET]
ws = wb.create_sheet(SHEET, index=wb.sheetnames.index(AFTER) + 1)
hdr, body = wb["Targets O vs A"]["A1"], wb["Targets O vs A"]["A2"]
wrap = Alignment(wrap_text=True, vertical="top")


def put(r, c, v, src, bold=False, size=None):
    cell = ws.cell(r, c, v)
    cell.font, cell.fill, cell.border = copy(src.font), copy(src.fill), copy(src.border)
    if bold or size:
        cell.font = Font(name=src.font.name, bold=True, size=size or src.font.size)
    cell.alignment = wrap


r = 1
for kind, *vals in PARTS:
    if kind == "title":
        put(r, 1, vals[0], body, size=14)
        r += 2
        continue
    if kind == "head":
        r += 1 if r > 3 else 0
        put(r, 1, vals[0], body, bold=True, size=12)
    elif kind == "text":
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
        put(r, 1, vals[0], body)
        ws.row_dimensions[r].height = 15 * (len(vals[0]) // 120 + 1)
    elif kind == "step":
        put(r, 1, vals[0], body, bold=True)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
        put(r, 2, vals[1], body)
        ws.row_dimensions[r].height = 15 * (len(vals[1]) // 100 + 1)
    elif kind == "table":
        for i, h in enumerate(vals[0], 1):
            put(r, i, h, hdr)
    elif kind == "row":
        for i, v in enumerate(vals[0], 1):
            put(r, i, v, body)
        ws.row_dimensions[r].height = 15 * (len(vals[0][2]) // 70 + 1)
    r += 1
for letter, w in zip("ABCD", (24, 18, 80, 30)):
    ws.column_dimensions[letter].width = w
wb.save(XLSX)
print("saved", XLSX, "rows", r - 1)
