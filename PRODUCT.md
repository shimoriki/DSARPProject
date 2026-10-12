<!-- impeccable:product-schema 1 -->

# Product

DSARP — an evidence-based refactoring agent for Java systems. It detects architectural smells
with established tools, proposes refactorings, applies them as real source changes, and then
re-measures with the same tool to say whether the architecture actually improved.

## Platform

web

## Users

- **The student team.** Runs the pipeline, reads the evidence, decides what to build next.
- **The supervising professor.** Reviews progress at intervals; needs to see what was built,
  what was measured, and what it means, without reading the code.
- **(Target, not yet served) a Java maintainer** who would receive a suggested refactoring and
  a before/after measurement rather than a raw smell report.

## Product Purpose

Close the loop that most smell tooling leaves open. A detector says a package is in a cycle; it
does not say what to change, and nothing checks whether the change helped. DSARP generates a
concrete source change, builds it, runs the tests, and re-runs the detector on the result.

## Positioning

Research instrumentation for a master's thesis, not a shipping product. Its value is the
measured evidence it produces, including negative results, and the discipline that makes those
numbers trustworthy.

## Operating Context

Windows workstation, 15.4 GB RAM. Java 8/17/26 installed, Maven 3.9.9 bundled in `tools/`.
Analysis runs take minutes to hours: a full Tika build and Arcan pass is roughly 20 minutes,
and a DistilBERT training run on CPU is about 30 minutes. Work happens in long background jobs.

## Capabilities and Constraints

Working today:
- Smell detection: Arcan 1.2.1 (bytecode) and DesigniteJava (source).
- History mining: RefactoringMiner 3.1.4.
- Dependency graphs from `jdeps` and ArchUnit, cross-checked against each other.
- Source transformation: OpenRewrite (Maven plugin 6.46.1) and Spoon 10.4.2.
- Validation gates: compile, test, and a same-tool before/after measurement.
- A second repository, `DSARP-OpenRewrite`, carrying a DistilBERT suggestion model and a
  local web dashboard.

Constraints:
- DesigniteJava runs here under a trial licence capped at 50,000 lines; above it the tool
  writes empty CSVs and exits zero, so larger repositories cannot be measured with it.
- `tika-grpc` cannot build on this machine (missing `protoc-gen-grpc-java`), so Tika is
  measured over the other 101 of 102 modules.
- The `DSARP-OpenRewrite` pipeline was written for macOS; running it here required porting.

## Brand Commitments

None recorded. No existing visual identity for the team's own communication artifacts; the
project's `DESIGN.md` documents system architecture, not a visual world.

## Evidence on Hand

All measured in this project, reproducible from committed code:
- Tika at commit `697d7c04`: **260 Arcan smells** before any change (173 cyclic, 86 unstable,
  1 hub-like), from 101 built modules and 1,804 class files.
- The supplied model's Tika output: 277 rows, every one returning the same five labels, with
  `Move Class` ranked first in **277 of 277**.
- Retrained from the supplied dataset: micro-F1 0.353, **macro-F1 0.039** over 18 labels;
  output moves by ≤0.001 when the smell type and every metric change.
- `Move Class` is 381 of 686 training rows (56%).
- The repository's own recipe generator turned 277 suggestions into **86** concrete moves;
  it discards 128 rows (46%) because it assumes package granularity and 178 of 249 named
  elements are classes.
- Earlier results: commons-validator 201 → 194 production smells with the stock OpenRewrite
  catalogue; 18 of 18 planned class moves applied, built, and removed their target edge;
  no cycle ever dissolved, in this work or in two expert-refactored reference trees.

## Product Principles

- **A number without a build is not a result.** A smell count falls reliably when the code
  stops compiling; any measurement from a tree that failed to build is void.
- **Before and after must differ only by the change.** Same tool version, same module set,
  same procedure.
- **Negative results are results.** Several of this project's firmest findings are things that
  did not work, and they are reported as prominently as the things that did.
- **Cite the evidence or mark it unsupported.** Suggestions carry evidence identifiers;
  anything unverified is labelled, never implied.

## Accessibility & Inclusion

Communication artifacts are read on a projector in a meeting room and on a laptop afterwards.
Text must survive projection: generous type size, strong contrast, no meaning carried by colour
alone, since architecture diagrams are frequently read from the back of a room.
