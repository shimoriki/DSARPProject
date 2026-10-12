/* DSARP interim review deck.
 *
 * Carries the transit world of the HTML deck: four route colours, one per concern, and route
 * lines with station ticks used only where they carry information (the pipeline, the attrition),
 * never as slide furniture. Arial and Calibri replace Barlow: PowerPoint renders fonts on the
 * reader's machine, and these two are the ones that measure true here.
 */
const pptxgen = require("pptxgenjs");

const THEME = {
  name: "DSARP Transit",
  headFontFace: "Arial",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "0F1419", lt1: "FFFFFF", dk2: "2B3440", lt2: "ECEFF2",
    accent1: "C6392C", accent2: "15589F", accent3: "B57A08", accent4: "237047",
    accent5: "4E5A66", accent6: "8A94A0",
    hlink: "15589F", folHlink: "6D2E46",
  },
};
const INK = "0F1419", PAPER = "FFFFFF", MUTE = "4E5A66", RULE = "C7CED4", TINT = "F2F5F7";
const RED = "C6392C", BLUE = "15589F", AMBER = "B57A08", GREEN = "237047";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";            // 13.3 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.author = "DSARP";
pres.title = "DSARP Interim Review";
const C = pres.SchemeColor;

const W = 13.3, H = 7.5, M = 0.7;

/* ---------- layouts ---------- */
pres.defineSlideMaster({
  title: "DARK", background: { color: INK },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 2.5, w: W - 2 * M, h: 1.6,
        fontSize: 44, bold: true, color: PAPER, fontFace: "Arial", charSpacing: -0.5,
        align: "left", valign: "bottom" }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: M, y: 4.2, w: 8.6, h: 1.9,
        fontSize: 16, color: "C8D0D8", fontFace: "Calibri" }, text: "" } },
  ],
});

pres.defineSlideMaster({
  title: "CONTENT", background: { color: PAPER },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.4, w: W - 2 * M, h: 1.05,
        fontSize: 32, bold: true, color: INK, fontFace: "Arial", charSpacing: -0.3,
        align: "left", valign: "top" }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: M, y: 1.55, w: W - 2 * M, h: 5.2,
        fontSize: 15, color: INK, fontFace: "Calibri" }, text: "" } },
    { text: { text: "DSARP interim review", options: { x: M, y: H - 0.52, w: 5, h: 0.3,
        fontSize: 9, color: MUTE, fontFace: "Calibri", isTextBox: true } } },
    { placeholder: { options: { name: "slideNum", type: "sldNum", x: W - 1.1, y: H - 0.52,
        w: 0.5, h: 0.3, fontSize: 9, color: MUTE, align: "right" } }, text: "" },
  ],
});

pres.defineSlideMaster({
  title: "TITLEONLY", background: { color: PAPER },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.4, w: W - 2 * M, h: 1.05,
        fontSize: 32, bold: true, color: INK, fontFace: "Arial", charSpacing: -0.3,
        align: "left", valign: "top" }, text: "" } },
    { text: { text: "DSARP interim review", options: { x: M, y: H - 0.52, w: 5, h: 0.3,
        fontSize: 9, color: MUTE, fontFace: "Calibri", isTextBox: true } } },
    { placeholder: { options: { name: "slideNum", type: "sldNum", x: W - 1.1, y: H - 0.52,
        w: 0.5, h: 0.3, fontSize: 9, color: MUTE, align: "right" } }, text: "" },
  ],
});

pres.defineSlideMaster({
  title: "DIVIDER", background: { color: TINT },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 3.0, w: W - 2 * M, h: 1.3,
        fontSize: 40, bold: true, color: INK, fontFace: "Arial", charSpacing: -0.4,
        align: "left" }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: M, y: 4.3, w: 8.4, h: 1.0,
        fontSize: 15, color: MUTE, fontFace: "Calibri" }, text: "" } },
  ],
});

/* ---------- helpers ---------- */
let S = null;
function slide(master, section) {
  S = pres.addSlide({ masterName: master, sectionTitle: section });
  return S;
}
function title(t) { S.addText(t, { placeholder: "title" }); }

function lede(t, y, w) {
  S.addText(t, { x: M, y: y, w: w || 11.4, h: 0.75, fontSize: 17, color: MUTE,
    fontFace: "Calibri", isTextBox: true, margin: 0, valign: "top" });
}

/** A route line with station ticks. Used only where the stations mean something. */
function route(x, y, len, color, stations, labelY) {
  S.addShape(pres.ShapeType.line, { x: x, y: y, w: len, h: 0,
    line: { color: color, width: 7 }, objectName: "route" });
  const step = stations.length > 1 ? len / (stations.length - 1) : 0;
  stations.forEach((st, i) => {
    const sx = x + step * i;
    S.addShape(pres.ShapeType.ellipse, { x: sx - 0.075, y: y - 0.075, w: 0.15, h: 0.15,
      fill: { color: PAPER }, line: { color: INK, width: 2 }, objectName: "tick" + i });
    S.addText(st.label, { x: sx - 0.95, y: labelY, w: 1.9, h: 0.6, fontSize: 10.5,
      color: INK, align: "center", fontFace: "Calibri", isTextBox: true, margin: 0 });
    if (st.fig) {
      S.addText(st.fig, { x: sx - 0.95, y: labelY + 0.52, w: 1.9, h: 0.34, fontSize: 13,
        bold: true, color: color, align: "center", fontFace: "Arial", isTextBox: true, margin: 0 });
    }
  });
}

/** Big measured figure with a caption under it. */
function stat(x, y, value, caption, color, w) {
  S.addText(value, { x: x, y: y, w: w || 2.5, h: 1.0, fontSize: 54, bold: true,
    color: color || INK, fontFace: "Arial", isTextBox: true, margin: 0, charSpacing: -1 });
  S.addText(caption, { x: x, y: y + 0.84, w: w || 2.5, h: 0.8, fontSize: 11, color: MUTE,
    fontFace: "Calibri", isTextBox: true, margin: 0 });
}

function table(rows, opts) {
  const o = Object.assign({
    x: M, y: 1.65, w: W - 2 * M, border: { type: "solid", color: RULE, pt: 0.5 },
    fontSize: 12.5, fontFace: "Calibri", color: INK, valign: "middle",
    autoPage: false, rowH: 0.34,
  }, opts || {});
  S.addTable(rows, o);
}
const TH = { fill: { color: INK }, color: PAPER, bold: true, fontSize: 11.5, fontFace: "Arial" };
function hdr(cells) { return cells.map(t => ({ text: t, options: Object.assign({}, TH) })); }
function cell(t, extra) {
  return { text: String(t), options: Object.assign({ fontSize: 12.5 }, extra || {}) };
}
function num(t, extra) {
  return cell(t, Object.assign({ align: "right", bold: true }, extra || {}));
}

function bullets(items, y, w, x) {
  S.addText(items.map((t, i) => ({ text: t, options: { bullet: true,
    breakLine: i < items.length - 1, paraSpaceAfter: 9 } })),
    { x: x || M, y: y, w: w || 11.9, h: 3.4, fontSize: 15, color: INK,
      fontFace: "Calibri", isTextBox: true, margin: 0, valign: "top" });
}

pres.addSection({ title: "Opening" });

slide("DARK", "Opening");
title("DSARP");
S.addText("An evidence-based refactoring agent for Java. It proposes a change, applies it, builds it, and then measures whether the architecture actually improved.",
  { placeholder: "body" });
S.addText("Interim progress review", { x: M, y: 1.75, w: 7, h: 0.4, fontSize: 15,
  color: AMBER, bold: true, fontFace: "Arial", isTextBox: true, margin: 0 });
S.addText("Nursapa et al., \u201cROSE,\u201d arXiv:2507.12561, 2025",
  { x: M, y: 6.78, w: 11.9, h: 0.3, fontSize: 10, color: "6B7480", italic: true,
    fontFace: "Calibri", isTextBox: true, margin: 0 });
S.addText("Apache Tika · Logging log4j2 · Apache Struts      Detector: Arcan 1.2.1",
  { x: M, y: 6.4, w: 11.9, h: 0.4, fontSize: 12, color: "8A94A0", fontFace: "Calibri",
    isTextBox: true, margin: 0 });
S.addNotes("Opening. The claim of the project is the loop: not just detecting smells but proving a change helped.");

/* ================= INTRO AND IDEA ================= */
pres.addSection({ title: "Intro and idea" });

slide("DIVIDER", "Intro and idea");
title("Intro and idea");
S.addText("What the project is for, and the gap it exists to close.", { placeholder: "body" });

slide("CONTENT", "Intro and idea");
title("A detector says where. It never says what to change");
S.addText([
  { text: "What the tools give us\n", options: { bold: true, fontSize: 15, color: RED, fontFace: "Arial", breakLine: true } },
  { text: "Arcan reports 252 architectural smells in Tika. Each names packages and a severity. None of them names an edit.", options: { fontSize: 15 } },
], { x: M, y: 1.7, w: 5.6, h: 2.0, color: INK, fontFace: "Calibri", isTextBox: true, margin: 0, valign: "top" });
S.addText([
  { text: "What is missing\n", options: { bold: true, fontSize: 15, color: AMBER, fontFace: "Arial", breakLine: true } },
  { text: "A concrete source change with real parameters. Proof it compiles and keeps the tests green. A second measurement, so “better” is a fact rather than a hope.", options: { fontSize: 15 } },
], { x: 7.0, y: 1.7, w: 5.6, h: 2.0, color: INK, fontFace: "Calibri", isTextBox: true, margin: 0, valign: "top" });
route(1.4, 5.2, 10.4, BLUE, [
  { label: "Detect" }, { label: "Propose" }, { label: "Apply" },
  { label: "Build & test" }, { label: "Re-measure" },
], 5.45);
S.addText("Only the last station is entitled to the word “better”.",
  { x: M, y: 6.5, w: 11.9, h: 0.4, fontSize: 12, italic: true, color: MUTE,
    fontFace: "Calibri", isTextBox: true, margin: 0 });
S.addNotes("The gap the project exists to close.");

slide("TITLEONLY", "Intro and idea");
title("Four concerns, in order");
const lanes = [
  ["Evidence", RED, "Detect smells; mine what maintainers really did."],
  ["Transformation", BLUE, "Turn a finding into a parameterised source change."],
  ["Validation", AMBER, "Compile it, test it, gate it."],
  ["Measurement", GREEN, "Re-run the same detector on the built result."],
];
lanes.forEach((L, i) => {
  const y = 1.9 + i * 1.18;
  S.addShape(pres.ShapeType.line, { x: M, y: y, w: 3.0, h: 0, line: { color: L[1], width: 9 } });
  S.addShape(pres.ShapeType.ellipse, { x: M + 2.93, y: y - 0.115, w: 0.23, h: 0.23,
    fill: { color: PAPER }, line: { color: INK, width: 2.5 } });
  S.addText(L[0], { x: 4.0, y: y - 0.26, w: 3.0, h: 0.5, fontSize: 19, bold: true,
    color: INK, fontFace: "Arial", isTextBox: true, margin: 0 });
  S.addText(L[2], { x: 7.0, y: y - 0.26, w: 5.6, h: 0.6, fontSize: 13.5, color: MUTE,
    fontFace: "Calibri", isTextBox: true, margin: 0 });
});
S.addText("Each hands its work to the next. The network map of all four is a separate artifact.",
  { x: M, y: 6.6, w: 11.9, h: 0.4, fontSize: 12, color: MUTE, fontFace: "Calibri",
    isTextBox: true, margin: 0 });


/* ================= C4 MODEL ================= */
pres.addSection({ title: "C4 model" });

slide("DIVIDER", "C4 model");
title("C4 model");
S.addText("The architecture of the pipeline itself, at three levels of zoom.", { placeholder: "body" });

slide("TITLEONLY", "C4 model");
title("What we built");
lede("Detectors, miners, two transformation backends, validation gates, and a matched before/after measurement.", 1.45);
route(1.5, 2.9, 10.2, BLUE, [
  { label: "Evidence", fig: "1" }, { label: "Transformation", fig: "2" },
  { label: "Validation", fig: "3" }, { label: "Measurement", fig: "4" },
], 3.15);
[["Arcan 1.2.1 \u00b7 RefactoringMiner 3.1.4 \u00b7 jdeps + ArchUnit", 1.5],
 ["OpenRewrite 6.46.1 \u00b7 Spoon 10.4.2 \u00b7 DistilBERT model", 4.9],
 ["Compile \u00b7 test \u00b7 residual \u00b7 coverage gates", 8.3],
 ["Arcan re-run, same config \u00b7 matched before/after diff", 11.7]].forEach(t =>
  S.addText(t[0], { x: t[1] - 1.5, y: 4.0, w: 3.0, h: 1.0, fontSize: 11.5, color: MUTE,
    fontFace: "Calibri", isTextBox: true, margin: 0, align: "center" }));
S.addText("Each stage hands its validated output to the next. The container-level map is the C4 model that follows.",
  { x: M, y: 5.6, w: 11.9, h: 0.4, fontSize: 13.5, color: INK, fontFace: "Calibri",
    isTextBox: true, margin: 0 });

slide("TITLEONLY", "C4 model");
title("The same system at three levels");
lede("A C4 model, so the pipeline can be read at the level the question needs. The interactive version is a separate artifact; these are its levels.", 1.45);
[["Level 1 \u00b7 Context", BLUE,
  "DSARP as one box. Who asks it for a change, and what it reads: a Java repository at a named commit, plus the detectors that judge it.",
  "Developer \u00b7 Java repository \u00b7 Arcan \u00b7 RefactoringMiner"],
 ["Level 2 \u00b7 Container", AMBER,
  "The four runnable concerns, each a separate process with its own inputs and outputs. This is the level the previous slide shows.",
  "Evidence \u00b7 Transformation \u00b7 Validation \u00b7 Measurement"],
 ["Level 3 \u00b7 Component", GREEN,
  "Inside Transformation: candidate generation from the dependency graph, ranking, recipe emission, and the OpenRewrite or Spoon run that applies it.",
  "generate_recipes \u00b7 ranking \u00b7 recipe plan \u00b7 executor"]
].forEach((c, i) => {
  const x = M + i * 4.0;
  S.addShape(pres.ShapeType.roundRect, { x: x, y: 2.2, w: 3.6, h: 3.5, rectRadius: 0.05,
    fill: { color: TINT }, line: { color: c[1], width: 1.5 } });
  S.addText(c[0], { x: x + 0.25, y: 2.4, w: 3.1, h: 0.4, fontSize: 16, bold: true,
    color: c[1], fontFace: "Arial", isTextBox: true, margin: 0 });
  S.addText(c[2], { x: x + 0.25, y: 2.85, w: 3.1, h: 1.9, fontSize: 12, color: INK,
    fontFace: "Calibri", isTextBox: true, margin: 0 });
  S.addText(c[3], { x: x + 0.25, y: 4.95, w: 3.1, h: 0.65, fontSize: 10.5, color: MUTE,
    fontFace: "Consolas", isTextBox: true, margin: 0 });
});
S.addText("One model, three zoom levels. Nothing in it is aspirational: every container named here runs today.",
  { x: M, y: 6.0, w: 11.9, h: 0.4, fontSize: 13.5, bold: true, color: INK,
    fontFace: "Calibri", isTextBox: true, margin: 0 });

slide("TITLEONLY", "C4 model");
title("What runs today");
table([
  hdr(["Capability", "Tool", "Status"]),
  [cell("Smell detection, bytecode"), cell("Arcan 1.2.1"), cell("\u25cf running", { color: GREEN, bold: true })],
  [cell("Smell detection, source"), cell("DesigniteJava"), cell("\u25cf trial licence, 50k line cap", { color: AMBER })],
  [cell("History mining"), cell("RefactoringMiner 3.1.4"), cell("\u25cf running", { color: GREEN, bold: true })],
  [cell("Dependency graphs"), cell("jdeps + ArchUnit, cross-checked"), cell("\u25cf running", { color: GREEN, bold: true })],
  [cell("Source transformation"), cell("OpenRewrite 6.46.1, Spoon 10.4.2"), cell("\u25cf running", { color: GREEN, bold: true })],
  [cell("Suggestion model"), cell("DistilBERT, multi-label"), cell("\u25cf trained and served", { color: GREEN, bold: true })],
  [cell("Validation gates"), cell("compile · test · residual · coverage"), cell("\u25cf running", { color: GREEN, bold: true })],
], { colW: [4.4, 4.6, 2.9], rowH: 0.44 });

slide("TITLEONLY", "C4 model");
title("What counts as a claim");
lede("The pipeline separates four kinds of statement. Only the last two support the sentence “this refactoring helped”.", 1.5);
const ladder = [
  ["1", "Model suggestion", "A ranked, probabilistic label. No parameters, no proof.", MUTE],
  ["2", "Concrete candidate", "Repository analysis supplied the parameters a recipe needs.", MUTE],
  ["3", "Validated refactoring", "Compiled, tested, passed the configured checks.", GREEN],
  ["4", "Measured result", "Before and after, same detector version, same configuration.", GREEN],
];
ladder.forEach((L, i) => {
  const y = 2.5 + i * 1.02;
  S.addShape(pres.ShapeType.ellipse, { x: M, y: y, w: 0.56, h: 0.56,
    fill: { color: L[3] === GREEN ? GREEN : "D9DEE3" } });
  S.addText(L[0], { x: M, y: y, w: 0.56, h: 0.56, fontSize: 17, bold: true,
    color: L[3] === GREEN ? PAPER : INK, align: "center", valign: "middle",
    fontFace: "Arial", isTextBox: true, margin: 0 });
  S.addText(L[1], { x: 1.5, y: y + 0.02, w: 3.4, h: 0.5, fontSize: 16, bold: true,
    color: INK, fontFace: "Arial", isTextBox: true, margin: 0 });
  S.addText(L[2], { x: 5.1, y: y + 0.04, w: 7.5, h: 0.5, fontSize: 13.5, color: MUTE,
    fontFace: "Calibri", isTextBox: true, margin: 0 });
});
S.addNotes("This ladder is why the negative findings are meaningful rather than embarrassing.");


/* ================= DASHBOARD ================= */
pres.addSection({ title: "Dashboard" });

slide("DIVIDER", "Dashboard");
title("Dashboard");
S.addText("The console that runs an experiment and records what each stage did.", { placeholder: "body" });

slide("TITLEONLY", "Dashboard");
title("Every run is a graph of stages you can inspect");
lede("The console runs an experiment as thirteen stages in four groups. Each stage records what it consumed, what it called and what it produced, so a run can be audited after the fact rather than trusted.", 1.45);
[["SETUP", BLUE, [["1", "Preflight", "Validate environment"], ["2", "Inputs", "Prepare model records"]]],
 ["LEARNING", AMBER, [["3", "Mining", "Extract history evidence"], ["4", "Training", "Train ranked model"], ["5", "Prediction", "Rank suggestions"]]],
 ["REPOSITORY", GREEN, [["6", "Clone", "Clone exact revision"], ["7", "Baseline", "Build and measure"]]],
 ["CHANGE & EVIDENCE", RED, [["8", "OpenRewrite", "Resolve, generate, validate"], ["9", "Focused tests", "Run targeted tests"], ["10", "Format", "Format and check diff"], ["11", "Final verify", "Verify whole project"], ["12", "Smells", "Compare architecture"], ["13", "Summary", "Present final evidence"]]]
].forEach((g, gi) => {
  const x = M + gi * 3.07;
  S.addShape(pres.ShapeType.line, { x: x, y: 2.45, w: 2.8, h: 0, line: { color: g[1], width: 4 } });
  S.addText(g[0], { x: x, y: 2.55, w: 2.8, h: 0.3, fontSize: 10.5, bold: true, color: g[1],
    fontFace: "Arial", isTextBox: true, margin: 0, charSpacing: 0.6 });
  g[2].forEach((s, si) => {
    const y = 2.9 + si * 0.60;
    S.addShape(pres.ShapeType.roundRect, { x: x, y: y, w: 2.8, h: 0.52, rectRadius: 0.04,
      fill: { color: PAPER }, line: { color: RULE, width: 1 } });
    S.addText(s[0] + " \u00b7 " + s[1], { x: x + 0.12, y: y + 0.03, w: 2.6, h: 0.25,
      fontSize: 11.5, bold: true, color: INK, fontFace: "Arial", isTextBox: true, margin: 0 });
    S.addText(s[2], { x: x + 0.12, y: y + 0.27, w: 2.6, h: 0.23, fontSize: 9.5, color: MUTE,
      fontFace: "Calibri", isTextBox: true, margin: 0 });
  });
});
S.addText("Stage 12 is the one that decides whether anything improved: it re-runs Arcan on the built tree and compares it with the baseline from stage 7.",
  { x: M, y: 6.55, w: 11.9, h: 0.4, fontSize: 12.5, color: INK, fontFace: "Calibri",
    isTextBox: true, margin: 0 });

/* ================= HOW SMELLS ARE PRESENTED ================= */
pres.addSection({ title: "How smells are presented" });

slide("DIVIDER", "How smells are presented");
title("How smells are presented");
S.addText("What a detector actually hands over, and how a single smell is identified across two runs.", { placeholder: "body" });

slide("TITLEONLY", "How smells are presented");
title("A smell is an identity, not a row");
lede("Arcan writes tables, not a list of problems. To say whether a particular smell survived a change, each one needs an identity that is stable across two runs. This is the identity the project uses.", 1.45);
table([
  hdr(["Smell", "Identified by", "Read from", "Count, all three systems"]),
  [cell("Cyclic Dependency"), cell("the set of packages, or classes, in the cycle"),
   cell("packageCyclicDependencyTable.csv, classCyclicDependencyTable.csv"), num("889")],
  [cell("Unstable Dependency"), cell("the (package, correlated package) pair"),
   cell("UD.csv"), num("300")],
  [cell("Hub-Like Dependency"), cell("the class"), cell("HL.csv"), num("4")],
], { y: 2.6, colW: [2.6, 3.4, 3.9, 2.0], rowH: 0.52 });
S.addText("The cycle tables are membership matrices: one row per cycle, one column per component, a 1 where that component belongs. A cycle is therefore the set of its members \u2014 which is why two runs can hold the same number of cycles and not one of them in common.",
  { x: M, y: 4.8, w: 11.9, h: 0.8, fontSize: 13, color: INK, fontFace: "Calibri",
    isTextBox: true, margin: 0 });
S.addText("UD30.csv is the same unstable dependencies filtered at 30% instability. It is a severity view of UD.csv and is deliberately not counted again \u2014 see the correction in Results.",
  { x: M, y: 5.75, w: 11.9, h: 0.8, fontSize: 13, bold: true, color: RED, fontFace: "Calibri",
    isTextBox: true, margin: 0 });

slide("TITLEONLY", "How smells are presented");
title("The same smell, as the console shows it");
lede("Each record carries the smell type, the exact elements it affects, and five ranked refactoring types with scores. This is the whole of what the model contributes.", 1.45);
S.addImage({ path: "img/dash-recommendations.jpg", x: 0.7, y: 2.05, w: 7.28, h: 4.5 });
S.addShape(pres.ShapeType.rect, { x: 0.7, y: 2.05, w: 7.28, h: 4.5,
  fill: { type: "none" }, line: { color: RULE, width: 1 } });
[
  ["Three cyclic dependencies", "Each names the packages in the cycle \u2014 three, four and six elements."],
  ["Move Class, every time", "Ranked first at 0.563 on all three, with near-identical runners-up."],
  ["No destination", "The record never says where to move the class to. The generator infers that separately."],
].forEach((n, i) => {
  S.addText(n[0], { x: 9.15, y: 2.1 + i * 1.28, w: 3.45, h: 0.4, fontSize: 14, bold: true,
    color: INK, fontFace: "Arial", isTextBox: true, margin: 0 });
  S.addText(n[1], { x: 9.15, y: 2.5 + i * 1.28, w: 3.45, h: 0.9, fontSize: 11.5, color: MUTE,
    fontFace: "Calibri", isTextBox: true, margin: 0 });
});
S.addText("Console: Predictions tab, Tika run, 277 generated prediction records.", { x: M, y: 6.65, w: 8.2, h: 0.4, fontSize: 11.5, italic: true, color: MUTE,
  fontFace: "Calibri", isTextBox: true, margin: 0 });

/* ================= SUGGESTIONS ================= */
pres.addSection({ title: "Suggestions" });

slide("DIVIDER", "Suggestions");
title("Suggestions, and where the tool fits");
S.addText("How a suggestion is produced, what it contains, and how far it gets.", { placeholder: "body" });

slide("TITLEONLY", "Suggestions");
title("The suggestion model");
lede("Trained here from the supplied dataset, using the repository's own notebook recipe.", 1.45);
[["In", "One sentence describing a smell, plus its metrics: type, severity, affected elements, edge count.", BLUE, M],
 ["DistilBERT", "Multi-label classifier trained on the supplied refactoring-history dataset. 686 rows, 18 labels.", AMBER, 4.75],
 ["Out", "Five refactoring type names with scores. Never a class, never a destination.", RED, 8.85]
].forEach(c => {
  S.addShape(pres.ShapeType.roundRect, { x: c[3], y: 2.5, w: 3.6, h: 2.0, rectRadius: 0.05,
    fill: { color: TINT }, line: { color: c[2], width: 1.5 } });
  S.addText(c[0], { x: c[3] + 0.25, y: 2.7, w: 3.1, h: 0.45, fontSize: 19, bold: true,
    color: c[2], fontFace: "Arial", isTextBox: true, margin: 0 });
  S.addText(c[1], { x: c[3] + 0.25, y: 3.2, w: 3.1, h: 1.2, fontSize: 12.5, color: INK,
    fontFace: "Calibri", isTextBox: true, margin: 0 });
});
S.addText("The gap between In and Out is the open question: a label is chosen without ever naming the code it applies to.",
  { x: M, y: 4.85, w: 11.9, h: 0.4, fontSize: 13.5, bold: true, color: INK,
    fontFace: "Calibri", isTextBox: true, margin: 0 });

slide("TITLEONLY", "Suggestions");
title("What it takes in, what it gives back");
S.addText([
  { text: "In\n", options: { bold: true, fontSize: 14, color: BLUE, fontFace: "Arial", breakLine: true } },
  { text: "One sentence describing a smell and its metrics: “Hub-like Dependency … affected elements org.apache.tika.utils … severity 24.0 … 24 edges …”", options: { fontSize: 14 } },
], { x: M, y: 1.7, w: 5.7, h: 1.8, color: INK, fontFace: "Calibri", isTextBox: true, margin: 0, valign: "top" });
S.addText([
  { text: "Out\n", options: { bold: true, fontSize: 14, color: BLUE, fontFace: "Arial", breakLine: true } },
  { text: "Five refactoring type names with scores. Never a class. Never a destination.", options: { fontSize: 14 } },
], { x: M, y: 3.5, w: 5.7, h: 1.2, color: INK, fontFace: "Calibri", isTextBox: true, margin: 0, valign: "top" });
table([
  hdr(["Held-out test", ""]),
  [cell("Rows / labels"), num("686 / 18")],
  [cell("micro-F1"), num("0.353")],
  [cell("macro-F1"), num("0.039", { color: RED })],
  [cell("top-1 hit rate"), num("0.534")],
  [cell("top-5 hit rate"), num("0.913")],
  [cell("macro-F1, across all 18 labels", { bold: true }), num("0.039", { color: RED })],
], { x: 7.0, y: 1.7, w: 5.6, colW: [3.6, 2.0], rowH: 0.44 });
S.addNotes("Macro-F1 of 0.039 over eighteen labels is the number that matters.");

slide("TITLEONLY", "Suggestions");
title("It answers the same thing every time");
table([
  hdr(["Input given to the model", "Move Class score"]),
  [cell("Hub-like Dependency, 24 edges, severity 24.0"), num("0.563")],
  [cell("Identical input, smell type changed to Cyclic"), num("0.564")],
  [cell("Unstable Dependency, every metric different"), num("0.563")],
], { colW: [8.8, 3.1], rowH: 0.46 });
S.addText("Changing the smell type and every numeric feature moves the answer by 0.001.",
  { x: M, y: 3.5, w: 11.9, h: 0.4, fontSize: 15, bold: true, color: INK,
    fontFace: "Calibri", isTextBox: true, margin: 0 });
stat(M, 4.15, "277 / 277", "rows where Move Class ranks first", RED, 3.4);
stat(4.6, 4.15, "381 / 686", "training rows carrying that same label", BLUE, 3.4);
stat(8.5, 4.15, "40 / 40", "rows where our retrain matches the supplied file", MUTE, 3.6);
S.addText("It learned the label prior, not a mapping from smell to fix.",
  { x: M, y: 6.5, w: 11.9, h: 0.4, fontSize: 12.5, italic: true, color: MUTE,
    fontFace: "Calibri", isTextBox: true, margin: 0 });


slide("TITLEONLY", "Suggestions");
title("Generation and validation, stage 8");
lede("The console shows what happened to each candidate: which recipes were generated, which executed, and which survived the build gate.", 1.45);
S.addImage({ path: "img/dash-validation.jpg", x: 0.7, y: 2.05, w: 7.36, h: 4.5 });
S.addShape(pres.ShapeType.rect, { x: 0.7, y: 2.05, w: 7.36, h: 4.5,
  fill: { type: "none" }, line: { color: RULE, width: 1 } });
[
  ["277 in, 3 executable", "Only three predictions resolved to a candidate the pipeline could run."],
  ["0 build-validated, 3 failed", "None of the three survived the build gate, so none can be claimed as an improvement."],
  ["All three are test code", "API impact test_only: the only resolvable moves were test classes."],
].forEach((n, i) => {
  S.addText(n[0], { x: 9.15, y: 2.1 + i * 1.28, w: 3.45, h: 0.4, fontSize: 14, bold: true,
    color: INK, fontFace: "Arial", isTextBox: true, margin: 0 });
  S.addText(n[1], { x: 9.15, y: 2.5 + i * 1.28, w: 3.45, h: 0.9, fontSize: 11.5, color: MUTE,
    fontFace: "Calibri", isTextBox: true, margin: 0 });
});
S.addText("The heap fallback note is real: Move Method resolution was unavailable on this machine.", { x: M, y: 6.65, w: 8.2, h: 0.4, fontSize: 11.5, italic: true, color: MUTE,
  fontFace: "Calibri", isTextBox: true, margin: 0 });

slide("TITLEONLY", "Suggestions");
title("From suggestion to something you can apply");
route(1.6, 2.35, 10.0, BLUE, [
  { label: "Suggestions", fig: "1,282" },
  { label: "Concrete moves", fig: "473" },
  { label: "Viable", fig: "354" },
  { label: "Comparable batches", fig: "17 of 31" },
  { label: "Reduced anything", fig: "2" },
], 2.6);
S.addText("Most of the loss has one cause. Of Tika's 249 named elements, 178 are classes rather than packages, and the generator only understands package granularity — so it discards 128 of 277 rows as “not present at this revision” when they are present, just at the wrong level.",
  { x: M, y: 4.0, w: 11.9, h: 0.9, fontSize: 14, color: INK, fontFace: "Calibri",
    isTextBox: true, margin: 0 });
S.addText("Every one of Tika's 86 surviving candidates is flagged high risk to the public API by the generator that produced it.",
  { x: M, y: 5.1, w: 11.9, h: 0.5, fontSize: 14, bold: true, color: RED,
    fontFace: "Calibri", isTextBox: true, margin: 0 });

/* ================= OUTPUT FROM THE TOOL ================= */
pres.addSection({ title: "Output from the tool" });

slide("DIVIDER", "Output from the tool");
title("Output from the tool");
S.addText("The prediction CSV and the rest of what a run produces.", { placeholder: "body" });

slide("TITLEONLY", "Output from the tool");
title("What one full run actually produced");
lede("A complete Tika run on the console, every stage green. These are its own reported figures, and they are the honest shape of the current result.", 1.45);
stat(M, 2.4, "277", "predictions processed", INK, 2.4);
stat(M + 2.6, 2.4, "3", "recipes generated", INK, 2.4);
stat(M + 5.2, 2.4, "3", "candidates executed", INK, 2.4);
stat(M + 7.8, 2.4, "0", "build-validated", RED, 2.4);
stat(M + 10.4, 2.4, "3", "failed", RED, 2.4);
S.addShape(pres.ShapeType.roundRect, { x: M, y: 4.5, w: 11.9, h: 1.15, rectRadius: 0.06,
  fill: { color: TINT }, line: { color: RED, width: 1.5 } });
S.addText("Refactoring outcome:  no validated refactoring", { x: 1.1, y: 4.72, w: 7.2, h: 0.45,
  fontSize: 20, bold: true, color: RED, fontFace: "Arial", isTextBox: true, margin: 0 });
S.addText("Pipeline status: completed. The run did not fail \u2014 it finished and reported that nothing it produced survived validation.",
  { x: 1.1, y: 5.15, w: 10.8, h: 0.4, fontSize: 12.5, color: INK, fontFace: "Calibri",
    isTextBox: true, margin: 0 });
S.addText("277 predictions in, 3 executable candidates out, 0 of them validated. The funnel on the Results slides measures the same collapse across all three systems.",
  { x: M, y: 5.95, w: 11.9, h: 0.5, fontSize: 13.5, bold: true, color: INK,
    fontFace: "Calibri", isTextBox: true, margin: 0 });

slide("TITLEONLY", "Output from the tool");
title("What a run leaves behind");
lede("Every run writes its inputs, its predictions, its validation report and its Arcan comparison to disk, each downloadable. The prediction CSV is the model's actual output.", 1.45);
S.addImage({ path: "img/dash-files.jpg", x: 0.7, y: 2.05, w: 7.2, h: 4.5 });
S.addShape(pres.ShapeType.rect, { x: 0.7, y: 2.05, w: 7.2, h: 4.5,
  fill: { type: "none" }, line: { color: RULE, width: 1 } });
[
  ["predictions.csv", "399 KB, 277 rows. Smell, affected elements, and five scored refactoring types."],
  ["validation-report.json", "Per-candidate outcome, including why each one was rejected."],
  ["arcan-comparison.json", "The before/after measurement that stage 12 produced."],
].forEach((n, i) => {
  S.addText(n[0], { x: 9.15, y: 2.1 + i * 1.28, w: 3.45, h: 0.4, fontSize: 14, bold: true,
    color: INK, fontFace: "Arial", isTextBox: true, margin: 0 });
  S.addText(n[1], { x: 9.15, y: 2.5 + i * 1.28, w: 3.45, h: 0.9, fontSize: 11.5, color: MUTE,
    fontFace: "Calibri", isTextBox: true, margin: 0 });
});
S.addText("Console: Files tab. Nothing here is generated for the slide; it is the run's own output.", { x: M, y: 6.65, w: 8.2, h: 0.4, fontSize: 11.5, italic: true, color: MUTE,
  fontFace: "Calibri", isTextBox: true, margin: 0 });

/* ================= RESULTS ================= */
pres.addSection({ title: "Results" });

slide("DIVIDER", "Results");
title("Results");
S.addText("Three systems, 1,193 distinct smells, 56 batches, every number from a tree that built.", { placeholder: "body" });

slide("TITLEONLY", "Results");
title("What the measurements say");
lede("Three systems, 1,193 baseline smells, 31 + 25 batches, every number from a tree that built.", 1.45);
stat(M, 2.5, "252", "Apache Tika, baseline smells", RED, 3.4);
stat(M + 4.0, 2.5, "714", "Logging log4j2, baseline smells", RED, 3.4);
stat(M + 8.0, 2.5, "227", "Apache Struts, baseline smells", RED, 3.4);
S.addText("1,193 distinct smells in all. Full baseline detail \u2014 commit, modules built, class counts \u2014 is on the next slide.",
  { x: M, y: 4.5, w: 11.9, h: 0.4, fontSize: 13.5, color: INK, fontFace: "Calibri",
    isTextBox: true, margin: 0 });

slide("TITLEONLY", "Results");
title("The baselines");
table([
  hdr(["System", "Commit", "Modules built", "Classes", "Arcan smells"]),
  [cell("Apache Tika"), cell("697d7c04"), num("101 of 102"), num("1,804"), num("252", { color: RED })],
  [cell("Logging log4j2"), cell("4f474b32"), num("41 of 41"), num("3,170"), num("714", { color: RED })],
  [cell("Apache Struts"), cell("d59aea5f"), num("24 of 27"), num("1,193"), num("227", { color: RED })],
], { colW: [3.2, 2.2, 2.4, 2.0, 2.1], rowH: 0.46 });
S.addText("Tika's 252 reconciles exactly against Arcan's raw output: 68 package cycles + 105 class cycles + 78 unstable + 1 hub-like. The 260 reported earlier added UD30.csv's 8 rows, which UD.csv already contains.",
  { x: M, y: 3.5, w: 11.9, h: 0.5, fontSize: 13.5, color: MUTE, fontFace: "Calibri",
    isTextBox: true, margin: 0 });
S.addText("Two modules cannot build on this machine for reasons unrelated to any refactoring: tika-grpc needs a protoc plugin, Struts 2 Tiles Plugin fails likewise. The same exclusion is applied to every later measurement, so before and after stay comparable.",
  { x: M, y: 4.2, w: 11.9, h: 0.8, fontSize: 13.5, color: MUTE, fontFace: "Calibri",
    isTextBox: true, margin: 0 });

slide("TITLEONLY", "Results");
title("Every total was double-counting");
lede("Arcan writes UD.csv and UD30.csv. UD30 is the same unstable dependencies filtered at a 30% instability threshold — a severity view of UD, not a second set of findings. The adapter globbed UD*.csv and read findings from both, so every severe unstable dependency was counted twice.", 1.45);
table([
  hdr(["System", "As first reported", "Distinct", "Rows counted twice"]),
  [cell("Apache Tika"), num("260"), num("252", { color: GREEN }), num("8")],
  [cell("Logging log4j2"), num("767"), num("714", { color: GREEN }), num("53")],
  [cell("Apache Struts"), num("274"), num("227", { color: GREEN }), num("47")],
], { y: 2.7, colW: [3.2, 3.0, 2.6, 3.1], rowH: 0.42 });
stat(M, 4.5, "63/63", "Arcan runs in which every UD30 pair was already present in UD. The subset holds without exception.", BLUE, 2.7);
stat(M + 3.1, 4.5, "37/37", "batches where the row count and the independent identity diff now agree exactly. Before the fix they disagreed on every affected batch.", GREEN, 2.7);
stat(M + 6.2, 4.5, "3", "verdicts that changed direction once restated, including one reduction that is really a worsening.", RED, 2.7);
stat(M + 9.3, 4.5, "−6", "the best result in the project, restated from −16. The duplicate count varies with the tree, so it never cancels in a delta.", AMBER, 2.7);
S.addText("The identity diff reported −6 where the row count reported −16. Chasing that gap instead of publishing the larger number is what exposed it.",
  { x: M, y: 6.55, w: 11.9, h: 0.5, fontSize: 14, bold: true, color: INK,
    fontFace: "Calibri", isTextBox: true, margin: 0 });

slide("TITLEONLY", "Results");
title("Two ways to choose the same operation");
lede("Both arms relocate classes. Arm B takes the model's label and lets the generator pick a destination. Arm C reads the real cycles from bytecode and computes what each move costs first. Same baselines, same batching, same build, same Arcan jar.", 1.45);
table([
  hdr(["System", "Arm", "Batches", "Comparable", "Reduced", "Worsened", "Best", "Removed"]),
  [cell("Tika"), cell("B · model"), num("14"), num("11"), num("0"), num("9"), num("0"), num("0.00%")],
  [cell("Tika"), cell("C · planner", { bold: true }), num("9"), num("8"), num("4", { color: GREEN }), num("4"), num("−12", { color: GREEN }), num("4.76%", { color: GREEN })],
  [cell("log4j2"), cell("B · model"), num("11"), num("5"), num("2"), num("3"), num("−6"), num("0.84%")],
  [cell("log4j2"), cell("C · planner"), num("6"), num("4"), num("1"), num("1"), num("−6"), num("0.84%")],
  [cell("Struts"), cell("B · model"), num("6"), num("1"), num("0"), num("1"), num("+27", { color: RED }), num("0.00%")],
  [cell("Struts"), cell("C · planner", { bold: true }), num("10"), num("8"), num("1", { color: GREEN }), num("6"), num("−15", { color: GREEN }), num("6.61%", { color: GREEN })],
], { y: 2.5, colW: [1.9, 2.0, 1.3, 1.6, 1.3, 1.5, 1.1, 1.2], rowH: 0.42 });
S.addText("Across 1,193 baseline smells arm B removed 6 at best and arm C removed 33. Arm C wins on two systems and ties log4j2. Neither selection is generally better.",
  { x: M, y: 5.6, w: 11.9, h: 0.7, fontSize: 14, color: INK, fontFace: "Calibri",
    isTextBox: true, margin: 0 });

slide("TITLEONLY", "Results");
title("The net figure hides the churn");
lede("Counting smells says nothing about whether the same ones survived. Matching them by identity — a cycle is the set of packages in it — tells a different story.", 1.45);
table([
  hdr(["Batch", "Moves", "Net", "Removed", "Created", "What actually happened"]),
  [cell("tika-B7"), num("1"), num("0"), num("10"), num("10"), cell("Reads as no change. Swapped ten smells for ten others.")],
  [cell("struts-C8"), num("1"), num("+26"), num("77"), num("103"), cell("One move dissolved 77 cycles and created 103.")],
  [cell("log4j2-B3"), num("25"), num("+16"), num("194"), num("210"), cell("Wholesale re-shuffle of the cycle structure.")],
  [cell("tika-C3"), num("12"), num("−12", { color: GREEN }), num("42"), num("30"), cell("Best Tika batch, and still created 30 new smells.")],
], { y: 2.5, colW: [1.5, 1.0, 1.0, 1.2, 1.2, 6.0], rowH: 0.46 });
S.addText("These operations do not improve an architecture incrementally. They re-partition it, and the count lands wherever the re-partition puts it.",
  { x: M, y: 5.3, w: 11.9, h: 0.7, fontSize: 15, bold: true, color: INK,
    fontFace: "Calibri", isTextBox: true, margin: 0 });

slide("TITLEONLY", "Results");
title("Even the wins usually make the cycles bigger");
lede("Eight batches reduced the smell count. For four, the cycles that replaced the removed ones were larger — and two finished with more package cycles than they started with.", 1.45);
table([
  hdr(["Batch", "Net smells", "Package cycles", "Removed, avg size", "Created, avg size"]),
  [cell("tika-C3"), num("−12"), num("68 → 64"), num("3.7"), num("4.5", { color: RED })],
  [cell("tika-C4"), num("−2"), num("68 → 73", { color: RED }), num("3.8"), num("4.6", { color: RED })],
  [cell("tika-C7"), num("−3"), num("68 → 71", { color: RED }), num("3.7"), num("4.4", { color: RED })],
  [cell("log4j2-B1"), num("−6"), num("201 → 199"), num("4.6"), num("5.4", { color: RED })],
  [cell("struts-C2", { bold: true }), num("−15", { color: GREEN }), num("87 → 75", { color: GREEN }), num("4.6"), num("4.5", { color: GREEN })],
  [cell("tika-C8", { bold: true }), num("−2", { color: GREEN }), num("68 → 67", { color: GREEN }), num("2.0"), num("none", { color: GREEN })],
], { y: 2.5, colW: [2.2, 2.2, 2.6, 2.5, 2.4], rowH: 0.42 });
S.addText("Fewer smells and a better structure are not the same measurement.",
  { x: M, y: 5.5, w: 11.9, h: 0.4, fontSize: 15, bold: true, color: INK,
    fontFace: "Calibri", isTextBox: true, margin: 0 });

slide("TITLEONLY", "Results");
title("The one change that improves on every measure");
S.addShape(pres.ShapeType.roundRect, { x: M, y: 1.6, w: 11.9, h: 2.2, rectRadius: 0.06,
  fill: { color: TINT }, line: { color: GREEN, width: 1.5 }, objectName: "cleanwin" });
S.addText("tika-C8", { x: 1.1, y: 1.85, w: 2.6, h: 0.5, fontSize: 24, bold: true,
  color: GREEN, fontFace: "Arial", isTextBox: true, margin: 0 });
S.addText("One class moved: org.apache.tika.server.core.MetadataList → server.core.writer",
  { x: 1.1, y: 2.4, w: 10.9, h: 0.4, fontSize: 15, color: INK, fontFace: "Calibri",
    isTextBox: true, margin: 0 });
S.addText("Removed one package cycle (server.core ↔ server.core.writer) and one unstable dependency. Created nothing. Package cycles 68 → 67. Build green.",
  { x: 1.1, y: 2.85, w: 10.9, h: 0.7, fontSize: 14, color: MUTE, fontFace: "Calibri",
    isTextBox: true, margin: 0 });
stat(M, 4.3, "2", "smells removed", GREEN, 2.0);
stat(3.0, 4.3, "0", "smells created", GREEN, 2.0);
stat(5.4, 4.3, "1", "class relocated", INK, 2.0);
stat(7.8, 4.3, "37", "comparable batches it was found among", MUTE, 3.0);
S.addText("MetadataList.java:    package org.apache.tika.server.core;    \u2192    package org.apache.tika.server.core.writer;",
  { x: M, y: 5.5, w: 11.9, h: 0.42, fontSize: 12.5, color: INK, fontFace: "Consolas",
    isTextBox: true, margin: 0.06, fill: { color: TINT } });
S.addText("Small, and the only change in 37 batches that improves on every measure taken.",
  { x: M, y: 6.4, w: 11.9, h: 0.4, fontSize: 13, italic: true, color: MUTE,
    fontFace: "Calibri", isTextBox: true, margin: 0 });

slide("TITLEONLY", "Results");
title("The matched comparison the console reports");
lede("Stage 12 re-runs Arcan on the built tree and matches it against the baseline. When nothing was validated, every delta is zero and the console says so.", 1.45);
S.addImage({ path: "img/dash-arcan-comparison.jpg", x: 0.7, y: 2.05, w: 7.67, h: 4.5 });
S.addShape(pres.ShapeType.rect, { x: 0.7, y: 2.05, w: 7.67, h: 4.5,
  fill: { type: "none" }, line: { color: RULE, width: 1 } });
[
  ["Every delta zero", "No validated change was applied, so the architecture is unchanged."],
  ["It refuses the causal claim", "Causal claim allowed: false. The tool will not let a null run read as a result."],
  ["UD and UD30 kept apart", "80 unstable and 8 filtered-at-30 are listed separately, never summed."],
].forEach((n, i) => {
  S.addText(n[0], { x: 9.15, y: 2.1 + i * 1.28, w: 3.45, h: 0.4, fontSize: 14, bold: true,
    color: INK, fontFace: "Arial", isTextBox: true, margin: 0 });
  S.addText(n[1], { x: 9.15, y: 2.5 + i * 1.28, w: 3.45, h: 0.9, fontSize: 11.5, color: MUTE,
    fontFace: "Calibri", isTextBox: true, margin: 0 });
});
S.addText("This is the behaviour the project wants: a run that achieves nothing must report nothing.", { x: M, y: 6.65, w: 8.2, h: 0.4, fontSize: 11.5, italic: true, color: MUTE,
  fontFace: "Calibri", isTextBox: true, margin: 0 });

slide("TITLEONLY", "Results");
title("What the discarded batches would have claimed");
lede("Of 56 batches run across both arms, 19 built a different module set from their baseline. Their counts are real Arcan output and every one is meaningless.", 1.45);
table([
  hdr(["Batch", "Modules built", "Smells read", "Would have read as"]),
  [cell("struts-B5, B6"), cell("4 of 24"), num("22"), num("−92%", { color: RED })],
  [cell("log4j2-B6, B9"), cell("9 of 41"), num("197–208"), num("−73%", { color: RED })],
  [cell("log4j2-B4"), cell("3 of 41"), num("627"), num("−18%", { color: RED })],
  [cell("tika-B1"), cell("84 of 101"), num("181"), num("−30%", { color: RED })],
], { y: 2.5, colW: [3.0, 2.8, 2.8, 3.3], rowH: 0.46 });
S.addText("A smell count falls reliably when code stops compiling. Without the module-set check this experiment would have reported improvements of up to 92% and been entirely wrong.",
  { x: M, y: 5.0, w: 11.9, h: 0.8, fontSize: 15, bold: true, color: INK,
    fontFace: "Calibri", isTextBox: true, margin: 0 });
S.addText("The guard is a result, as much as the percentages are.",
  { x: M, y: 5.9, w: 11.9, h: 0.4, fontSize: 13, italic: true, color: MUTE,
    fontFace: "Calibri", isTextBox: true, margin: 0 });

slide("TITLEONLY", "Results");
title("What has been measured and held");
table([
  hdr(["Result", "Evidence"]),
  [cell("Stock static analysis on commons-validator"), cell("201 → 194 production smells, compiles, 1,147 tests green")],
  [cell("With a custom magic-number recipe added"), cell("201 → 190, nothing introduced, same tests green")],
  [cell("Planned class moves"), cell("18 of 18 applied, built, and removed their target edge")],
  [cell("Predicting a move's cost before making it"), cell("Added edges exact on 14 of 18, within one on 18 of 18")],
  [cell("Package splitting"), cell("0 of 4 accepted; predicted 0 better, 77 worse")],
  [cell("Dissolving a dependency cycle"), cell("Never achieved — here, or in two expert-refactored trees")],
], { colW: [5.4, 6.5], rowH: 0.48 });
S.addText("Every figure comes from a run in this repository and is reproducible from committed code.",
  { x: M, y: 5.3, w: 11.9, h: 0.4, fontSize: 12.5, italic: true, color: MUTE,
    fontFace: "Calibri", isTextBox: true, margin: 0 });


/* ================= CONCLUSIONS AND DRAWBACKS ================= */
pres.addSection({ title: "Conclusions and drawbacks" });

slide("DIVIDER", "Conclusions and drawbacks");
title("Conclusions and drawbacks");
S.addText("What the measurements changed in our thinking, and what is still open.", { placeholder: "body" });

slide("TITLEONLY", "Conclusions and drawbacks");
title("What the measurements changed in our thinking");
const learns = [
  [BLUE, "A label is not a refactoring.", "The gap between “Move Class” and a compiling edit is where almost all of the engineering lives."],
  [AMBER, "The detector's count is not the goal.", "Across six repositories and 2,085 findings only about 28% are reachable at all; the rest is published API, test code, or a warning the maintainers deliberately suppressed."],
  [RED, "Edge arithmetic does not predict the verdict.", "The planner's prediction is exact on edges and correlates only +0.38 with the measured smell delta; 7 of 19 batches predicted to improve actually did."],
  [GREEN, "Improvement must be measured on a tree that builds.", "Three separate times a broken build produced a number that looked like success."],
];
learns.forEach((L, i) => {
  const y = 1.7 + i * 1.25;
  S.addShape(pres.ShapeType.ellipse, { x: M, y: y + 0.05, w: 0.34, h: 0.34, fill: { color: L[0] } });
  S.addText(L[1], { x: 1.3, y: y, w: 11.3, h: 0.42, fontSize: 16, bold: true, color: INK,
    fontFace: "Arial", isTextBox: true, margin: 0 });
  S.addText(L[2], { x: 1.3, y: y + 0.42, w: 11.3, h: 0.75, fontSize: 13.5, color: MUTE,
    fontFace: "Calibri", isTextBox: true, margin: 0 });
});

slide("TITLEONLY", "Conclusions and drawbacks");
title("Where this stands");
lede("Four statements, separated by how much evidence stands behind each.", 1.45);
[["Evidence + transformation", GREEN, "built, running",
  "Detectors, miners and both transformation backends (OpenRewrite, Spoon) operate end to end on all three systems."],
 ["Validation + matched measurement", GREEN, "built, running",
  "Compile, test, residual and coverage gates plus the module-build guard are in place; 56 batches run across both arms."],
 ["Suggestion model", RED, "open problem",
  "Macro-F1 0.039 over 18 labels means it is not yet mapping smells to fixes. Rebalancing the training corpus is the next task, not a future nice-to-have."],
 ["Thesis framing", AMBER, "open, for this meeting",
  "Smell reduction, or a trustworthy verdict on whether a refactoring helped. The two questions at the end of this deck."]
].forEach((r, i) => {
  const y = 2.3 + i * 1.12;
  S.addShape(pres.ShapeType.rect, { x: M, y: y, w: 0.06, h: 0.92, fill: { color: r[1] } });
  S.addText(r[0], { x: M + 0.25, y: y, w: 4.3, h: 0.4, fontSize: 16, bold: true, color: INK,
    fontFace: "Arial", isTextBox: true, margin: 0 });
  S.addText(r[2], { x: M + 0.25, y: y + 0.4, w: 4.3, h: 0.35, fontSize: 12.5, bold: true,
    color: r[1], fontFace: "Arial", isTextBox: true, margin: 0 });
  S.addText(r[3], { x: 5.6, y: y, w: 7.0, h: 0.95, fontSize: 12.5, color: MUTE,
    fontFace: "Calibri", isTextBox: true, margin: 0 });
});
S.addText("Three of the four are measured and reproducible. The fourth is the one we would like your steer on.",
  { x: M, y: 6.85, w: 11.9, h: 0.4, fontSize: 13, bold: true, color: INK, fontFace: "Calibri",
    isTextBox: true, margin: 0 });

slide("TITLEONLY", "Conclusions and drawbacks");
title("Two decisions we would like your view on");
S.addShape(pres.ShapeType.roundRect, { x: M, y: 1.6, w: 5.75, h: 4.3, rectRadius: 0.05,
  fill: { color: TINT }, line: { color: RULE, width: 1 }, objectName: "q1" });
S.addText("1", { x: 1.0, y: 1.85, w: 0.6, h: 0.6, fontSize: 30, bold: true, color: BLUE,
  fontFace: "Arial", isTextBox: true, margin: 0 });
S.addText("Should the thesis target smell reduction, or a trustworthy verdict on whether a proposed refactoring helps?",
  { x: 1.0, y: 2.5, w: 5.1, h: 1.3, fontSize: 16, bold: true, color: INK,
    fontFace: "Calibri", isTextBox: true, margin: 0 });
S.addText("The second is what the pipeline measurably does well. The first is what the literature usually promises, and our evidence bounds it at roughly a quarter of what a detector reports.",
  { x: 1.0, y: 3.9, w: 5.1, h: 1.7, fontSize: 13.5, color: MUTE, fontFace: "Calibri",
    isTextBox: true, margin: 0 });
S.addShape(pres.ShapeType.roundRect, { x: 6.85, y: 1.6, w: 5.75, h: 4.3, rectRadius: 0.05,
  fill: { color: TINT }, line: { color: RULE, width: 1 }, objectName: "q2" });
S.addText("2", { x: 7.15, y: 1.85, w: 0.6, h: 0.6, fontSize: 30, bold: true, color: BLUE,
  fontFace: "Arial", isTextBox: true, margin: 0 });
S.addText("Is a negative, well-measured result an acceptable primary contribution here?",
  { x: 7.15, y: 2.5, w: 5.1, h: 1.3, fontSize: 16, bold: true, color: INK,
    fontFace: "Calibri", isTextBox: true, margin: 0 });
S.addText("We can state precisely why the suggestion model carries no information about the specific smell, and precisely where the pipeline loses 191 of 277 suggestions. Both are reproducible.",
  { x: 7.15, y: 3.9, w: 5.1, h: 1.7, fontSize: 13.5, color: MUTE, fontFace: "Calibri",
    isTextBox: true, margin: 0 });

/* ================= FUTURE WORK ================= */
pres.addSection({ title: "Future work" });

slide("DIVIDER", "Future work");
title("Future work");
S.addText("What happens next, in the order we would do it.", { placeholder: "body" });

slide("TITLEONLY", "Future work");
title("Next");
S.addText("Immediate", { x: M, y: 1.6, w: 5.6, h: 0.4, fontSize: 15, bold: true,
  color: AMBER, fontFace: "Arial", isTextBox: true, margin: 0 });
bullets([
  "Teach the recipe generator class granularity, which alone unlocks 128 of the 277 discarded Tika suggestions.",
  "Give the generator a visibility screen, so it stops proposing moves that cannot compile anywhere.",
  "Re-run the 19 void batches with a larger heap so the module sets match.",
], 2.05, 5.6);
S.addText("Then", { x: 7.0, y: 1.6, w: 5.6, h: 0.4, fontSize: 15, bold: true,
  color: GREEN, fontFace: "Arial", isTextBox: true, margin: 0 });
bullets([
  "Rebalance the training corpus so the model stops answering with the majority label.",
  "Score candidates on cycle participation and cycle size, not on the raw smell count.",
  "Extend the measured corpus beyond the repositories the current licence allows.",
], 2.05, 5.6, 7.0);
S.addText("The clean win, tika-C8, is the shape to aim for: a single move that removes smells and creates none.",
  { x: M, y: 5.6, w: 11.9, h: 0.5, fontSize: 14, italic: true, color: MUTE,
    fontFace: "Calibri", isTextBox: true, margin: 0 });

pres.addSection({ title: "Close" });

slide("DARK", "Close");
title("Thank you");
S.addText("Every number in this deck comes from a run on one machine, against the commits named, with Arcan 1.2.1, and is reproducible from committed code. Where a measurement was discarded, the deck says so rather than reporting it.",
  { placeholder: "body" });
[["1,193", "baseline smells"], ["56", "batches run"], ["37", "comparable"],
 ["2", "clean wins"]].forEach((c, i) => {
  S.addText(c[0], { x: M + i * 3.0, y: 5.2, w: 2.8, h: 0.8, fontSize: 38, bold: true,
    color: AMBER, fontFace: "Arial", isTextBox: true, margin: 0, charSpacing: -1 });
  S.addText(c[1], { x: M + i * 3.0, y: 6.0, w: 2.8, h: 0.4, fontSize: 12,
    color: "8A94A0", fontFace: "Calibri", isTextBox: true, margin: 0 });
});

/* ---------- write ---------- */
(async () => {
  await pres.writeFile({ fileName: "DSARP_interim_review.pptx" });
  // applyTheme rewrites the master's theme1.xml colour scheme. Every text element in this deck
  // already carries an explicit fontFace and colour, so the deck is correct without it; it is
  // skipped rather than fatal when the pptx skill is not installed in this environment.
  try {
    const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");
    await applyTheme("DSARP_interim_review.pptx", THEME);
    console.log("written DSARP_interim_review.pptx (theme applied)");
  } catch (e) {
    console.log("written DSARP_interim_review.pptx (theme step skipped: "
                + (process.env.PPTX_SKILL ? e.code || e.message : "PPTX_SKILL unset") + ")");
  }
})();
