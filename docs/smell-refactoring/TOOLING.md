# Tooling: what the field uses, and what we should adopt

Written 2026-09-13, after measuring 86 candidates across four repositories with three
operations. This is a decision document, not a survey: every tool gets a verdict and a cost.

The field assembles an automated refactoring pipeline out of five stages. We have something in
each, so the question at every stage is *keep, add, or replace* — never "what exists".

| stage | ours | verdict |
|---|---|---|
| detect | Arcan 1.2.1 (+ Designite) | **keep** — precision is what a measurement instrument needs |
| transform | Spoon 10.4.2, OpenRewrite 8.37 | **keep both**, add Eclipse JDT for one job |
| decide legality | hand-written precheck | **replace** — this is the leak |
| validate | compile + project tests | **add** EvoSuite regression oracles |
| select / rank | ATDI severity, graph heuristics | **replace** — measurably anti-predictive |
| mine examples | RefactoringMiner 3.1.4 | keep, add synthetic injection |

---

## 1. Detection — keep Arcan

**What others use.** Commercial tools (Sonargraph, Structure101, Sotograph, CAST) and research
tools (Arcan, HotspotDetector, Designite, STAN, Massey Architecture Explorer). Designite
detects the *highest number* of architectural smells of the tools compared in the literature.

**The methodological split that matters to us.** Most tools — Designite, Sonargraph, STAN,
Structure101 — detect at the **class level** and then generalise to packages. **Arcan and
HotspotDetector treat packages and classes as distinct elements and do a two-layer analysis.**

**Verdict: keep Arcan, and this is now a principled choice rather than an inherited one.**
Every operation we have acts on a *package edge* — `moveClass` relocates across packages,
`invertEdge` inverts a package dependency. A detector that models packages natively is
measuring the thing we manipulate. One that generalises up from classes would report changes
we did not make and miss ones we did.

Arcan's reported **100% precision, 63% recall** also suits the role. As a measurement
instrument, precision is the property that matters: a false positive means we refactor
something that was never broken and the run is wasted, while a false negative only means we
leave a smell alone. Low recall makes our baselines *conservative* — there are smells in these
repositories that Arcan does not count, so our reduction rates are not inflated by them.

**Do not switch to Designite for measurement.** "Detects more smells" is a liability here, not
a feature: a wider net with unknown precision changes the denominator of every rate we have
already measured, invalidating the 86-candidate corpus for no gain.

---

## 2. Transformation — keep Spoon and OpenRewrite

**Settled empirically this week.** Identical moves through both backends: Spoon 5/5 compiled,
OpenRewrite 2/5 → **5/5 after fixing our own pipeline**, with per-candidate agreement exact on
all five. The gap was never capability. See `COUNTERMEASURES.md` §3.

**Verdict: keep both.** They are interchangeable on the operations we have, and keeping two
backends is what made the pipeline bugs findable — the disagreement was the signal.

**What we do NOT need.** JavaParser/JavaSymbolSolver would be a third AST library with less
type resolution than Spoon already gives us. IntelliJ's refactoring engine is not distributable
headlessly. Neither earns its integration cost.

---

## 3. Legality — replace our precheck with Eclipse JDT (the one big recommendation)

**This is where we are weakest, and the fix already exists.**

Our `extractIllegalReason` is a hand-written checklist. It has leaked four times, each found by
a real build failure, each patched reactively:

1. value escapes through an invocation argument,
2. …through an assignment to a field declared elsewhere,
3. …through an overridden method's return type,
4. consumer-package **subclassing** (`PDImageXObject extends PDXObject` → 92 symbol errors).

And it is still leaking: `CFFFont` failed again after all four, most likely through generic
containers (`List<CFFFont>`), where the argument's top-level type is `java.util.List` and the
check never sees the class at all. Casts, wildcards and bounded type parameters are further
routes nobody has hit yet.

**This is a named, solved problem.** Deciding which references to a class can be retargeted to
an interface is the **type constraints** problem, and Eclipse JDT has implemented it since the
original Extract Interface work. The release note is precise about it: the refactoring changes
references to the class into references to the new interface *"where possible"* — that
qualifier is exactly the constraint computation we are failing to reproduce.

**And it is drivable without a GUI.** Two facts make this feasible:

- `org.eclipse.jdt.core.manipulation` exists specifically to hold the display-independent
  refactoring logic, separated from `org.eclipse.jdt.ui`, **so that other tools can reuse it in
  headless environments**. That is the bundle's stated purpose.
- The API is programmatic:
  `RefactoringCore.getRefactoringContribution(IJavaRefactorings.EXTRACT_INTERFACE)` →
  `createDescriptor()` → set arguments → `validateDescriptor()` → `createRefactoringContext()`
  → execute. `ExtractInterfaceDescriptor` is a documented public type and the refactoring id is
  `org.eclipse.jdt.ui.extract.interface`.

**The cost is real and should not be understated.** JDT's parser and formatter run in a plain
`main()`, but the AST rewriter and search index **require a workspace, which means an OSGi
runtime**. So this is embedding Equinox or running an Eclipse headless application, not adding
a jar. Estimate 1–2 days, with genuine risk of yak-shaving on the workspace setup.

**Verdict: integrate, scoped to legality and reference updating for Extract Interface only.**
Keep Spoon as the transformation engine for `moveClass`, which is working. The argument is not
that JDT is nicer; it is that we are hand-rolling a constraint solver, badly, and a correct one
is sitting in a bundle designed to be reused headlessly.

**Cheap interim alternative (~1 hour).** If the OSGi work is not worth it yet: only abstract
declarations that cannot escape — private fields and locals, plus parameters and returns of
private methods. Provably safe, no constraint solving, and it cuts fewer edges. Worth doing as
a stopgap precisely because it is honest about what it gives up.

---

## 4. Validation — add EvoSuite, keep the project's own tests

**What others use.** Compiling and running the project's suite is the standard, and the
literature is blunt that it is insufficient: it "may fail to capture more subtle behavioral
deviations, and many developers' test suites are insufficient". **SAFEREFACTOR** is the named
countermeasure — compile, generate tests with **Randoop** for the methods the change affects,
run them before and after.

**We have independent evidence for this.** Tika's `ServiceLoaderUtilsTest.testSort` caught a
move that compiled cleanly and silently reordered service dispatch, because Tika sorts
implementations by fully-qualified class name. Compilation and the smell metric both said yes.
Only a test caught it — and only because Tika happened to have that test.

**Randoop or EvoSuite?** Both are used for refactoring validation; the comparative study
applies both to detecting Extract Method faults. For *our* job, **EvoSuite** is the better fit:
it is search-based rather than feedback-directed random, and it **generates assertions that
concisely summarise current behaviour**. That is precisely a regression oracle — capture
behaviour before, replay after. Randoop is what SAFEREFACTOR used, but oracle generation is the
feature we actually need.

**Verdict: integrate EvoSuite, scoped to the types the refactoring touched.** Generate against
the baseline, run against the refactored tree. Do not generate for the whole repository — on
Tika that would be 123 modules of generation per candidate.

**Carry the caveat into the report.** The same literature notes generated suites "can be
ineffective regarding fault detection". This raises our confidence; it does not make
behaviour preservation a solved problem, and the report should not claim it does.

---

## 5. Selection and ranking — replace, highest value per hour

**Our current ranking is measurably anti-predictive.** Trialling PDFBox candidates in ATDI
order: the high-severity half produced 2/12 wins and **+12 smells**; the low-severity half
produced 6/13 and **−273**. The detector's severity score points away from the fixable work.

**The field already knows severity alone ranks badly** — there is published work specifically
on *balancing severity against importance* of refactoring opportunities, and separate work
reporting that the criteria recommendation tools rank by are not the criteria practitioners
use.

**What others use instead: multi-objective search.** MORE (NSGA-III) optimises design quality,
smell correction and design-pattern introduction together; Ouni et al. use NSGA-II over quality
and modification effort; robustness variants add "do not introduce new defects" as an explicit
objective and return a Pareto front rather than one answer. Implementations are standard
(jMetal).

**Verdict: do the simple version first, and do not reach for a genetic algorithm yet.** We have
86 measured outcomes. Rank by **predicted total smell reduction** learned from those labels.
Two reasons to stay simple:

- Value is extremely concentrated — `MissingOperandException` alone was −240 of −289 smells
  removed. Expected-value ranking captures that; a hit-rate objective does not.
- A Pareto front needs objectives we can evaluate cheaply, and ours costs a compile plus an
  Arcan run per point. NSGA-II over that is thousands of builds.

Multi-objective search becomes appropriate once a *predictor* makes evaluation cheap. It is the
second step, not the first.

---

## 6. Mining — keep RefactoringMiner, add injection

RefactoringMiner is the standard and we already use it. Its limit for us is volume: Extract
Interface yields 6 instances, Split Package 1.

The field's answer is **synthetic generation by injecting smells** — take clean code, move a
class where it does not belong, and you have a labelled instance with known ground truth;
explicitly proposed for building datasets large enough to train on. We can run our own pipeline
backwards to produce these, which makes it cheap.

**Verdict: add, clearly labelled, reported separately.** Synthetic instances test *recovery of
an injected fault*, which is an easier problem than finding a real one. Mixing them into a
headline number would overstate the system.

---

## 7. Where our architecture already matches best practice

Recorded because these were reached by failure, not by reading:

- **Enumerate-and-pick.** We stopped letting the model author edits and made it choose among
  pre-validated candidates. The LLM study measures exactly this: ChatGPT identified 15.6% of
  opportunities unconstrained and **86.7%** when the prompt narrowed the search space.
- **Validate by applying.** ROSE reports 96.9% accuracy classifying which method suits a smell
  and never applies anything. That number does not predict whether the smell goes away.
- **Multi-agent with compile + test gates** is what RefAgent (2025) also does — same shape,
  same metrics (compilation rate, test pass rate, success rate).
- **Per-candidate attribution.** Batched runs hid four good moves behind one bad one.
- **Keep the logs.** Two OpenRewrite failures were unexplained for a whole run because the work
  directory was deleted.

---

## Integration plan, ordered by value per hour

| # | action | cost | why now |
|---|---|---|---|
| 1 | Rank by predicted total reduction from the 86 labels | 1–1.5h + 1h run | 2× measured signal; ATDI is anti-predictive |
| 2 | Conservative legality stopgap (private fields/locals only) | ~1h | stops the leak today, honestly scoped |
| 3 | EvoSuite oracles for touched types | 2–3h | the Tika ServiceLoader class of bug |
| 4 | Synthetic injection for thin methods | 1–2h | unblocks Extract Interface training data |
| 5 | **Eclipse JDT `core.manipulation` for Extract Interface legality** | 1–2 days | the correct fix; replaces a leaking checklist |
| 6 | Multi-objective search (jMetal) | days | only once a predictor makes evaluation cheap |

Items 1–4 are a day's work for most of the available gain. Item 5 is the one that changes what
the system can soundly claim. Item 6 should wait.

---

## Sources

- [Arcan: a Tool for Architectural Smells Detection](https://boa.unimib.it/retrieve/e39773b3-de57-35a3-e053-3a05fe0aac26/PID4705339.pdf)
- [Architectural Smells Detected by Tools: a Catalogue Proposal](https://www.researchgate.net/publication/331802822_Architectural_Smells_Detected_by_Tools_a_Catalogue_Proposal)
- [ExtractInterfaceDescriptor (Eclipse JDT API)](https://help.eclipse.org/latest/topic/org.eclipse.jdt.doc.isv/reference/api/org/eclipse/jdt/core/refactoring/descriptors/ExtractInterfaceDescriptor.html)
- [IJavaRefactorings (Eclipse JDT API)](https://help.eclipse.org/latest/topic/org.eclipse.jdt.doc.isv/reference/api/org/eclipse/jdt/core/refactoring/IJavaRefactorings.html)
- [Extract Interface refactoring released (jdt-ui-dev)](https://www.eclipse.org/lists/jdt-ui-dev/msg00387.html)
- [JDT/FAQ — Eclipsepedia (headless use, core.manipulation)](https://wiki.eclipse.org/JDT/FAQ)
- [JDT without Eclipse](https://jmini.github.io/blog/2020/2020-01-17_jdt-without-eclipse.html)
- [Automated Behavioral Testing of Refactoring Engines (SAFEREFACTOR)](https://www.microsoft.com/en-us/research/wp-content/uploads/2020/08/tse12.pdf)
- [Analyzing Automatic Test Generation Tools for Refactoring Validation](https://www.researchgate.net/publication/345729160_Analyzing_Automatic_Test_Generation_Tools_for_Refactoring_Validation)
- [EvoSuite: Automatic Test Suite Generation for Java](https://www.evosuite.org/)
- [MORE: A multi-objective refactoring recommendation approach](https://onlinelibrary.wiley.com/doi/abs/10.1002/smr.1843)
- [A robust multi-objective approach to balance severity and importance](https://link.springer.com/article/10.1007/s10664-016-9426-8)
- [RefAgent: A Multi-agent LLM-based Framework for Automatic Software Refactoring](https://arxiv.org/pdf/2511.03153)
- [An Empirical Study on the Potential of LLMs in Automated Software Refactoring](https://arxiv.org/abs/2411.04444)
- [Mind the Gap: Refactoring Criteria in Industry vs Recommendation Tools](https://www.researchgate.net/publication/387239150_Mind_the_Gap_The_Disconnect_Between_Refactoring_Criteria_Used_in_Industry_and_Refactoring_Recommendation_Tools)
