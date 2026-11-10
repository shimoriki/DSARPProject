# Final build plan: DSARP Cycle-Repair Loop

Requirements: `.claude/prds/dsarp-cycle-repair-loop.prd.md`. Evidence: `docs/ARCHITECTURE_SMELL_REDESIGN.md`.
Evidence labels ([M], [R], [C], [P], [S], [U]) are defined there. Nothing here has been built or run yet.

## 1. The final choice

**Project:** DSARP, continued from `claude/infallible-wescoff-ee351b` (`f82d2ca`).
Not DSARP-OpenRewrite, not DSARP Studio, not a rewrite.

**Approach:** deterministic predicted-first repair. Bytecode graph explains each cycle. Arithmetic
predicts each move before anything runs. Spoon applies it in a disposable copy. Tests decide acceptance.
The same detector and two bytecode readers verify the result.

```text
detect -> explain -> predict -> apply one change -> compile -> verify edge
       -> check API and dispatch -> run tests -> assign level -> ledger
```

**How it fixes and automates refactoring:**

| Step | What it automates | What it fixes |
|---|---|---|
| Detect | Finds cycles without human reading | Gives the oracle |
| Explain | Names the classes carrying each package edge | Label models could not say what to change |
| Predict | Computes edges removed and added | Stops moves that make the graph worse: 59 of 220 did [M] |
| Apply | Moves the class and rewrites references | Removes manual edits and parameter guessing |
| Verify | Re-measures named edge and cycle | Replaces smell totals that move by chance |
| Test | Compares against own baseline | Catches moves that compile but change behavior |
| Ledger | Records every rejection and reason | Keeps failures as evidence |

**What it will not do:** dissolve giant SCCs, or prove behavior preservation. Tests are a floor.

## 2. References: where each part comes from

"Used in" is where the idea or tool was applied. "Our use" is its job here.

### Reused from this project (branch `f82d2ca`)

| Component | File | Used in | What it does | Basis |
|---|---|---|---|---|
| Move prediction | `dsarp/tools/jdeps_runner.py` `move_effect`; `dsarp/refactoring/move_planner.py` | pdfbox, log4j2, tika | Relabels a class, re-derives package graph, diffs. Exact 14/18 | [C, R] |
| Group relabel | `move_planner.package_edges_after`, `participation` | Commons Compress expert-tree analysis | Accepts a class set; computes packages in cycles | [C, R] |
| Edge oracle | `dsarp/tools/archunit_runner.py` `edge_verdict`, `novel_cycles` | Same 3 repos | Says if edge is gone, its cost, new cycles | [C, R] |
| Second reader | `jdeps_runner.cross_check` | Same | Independent check; agreed 13 of 13 | [C, R] |
| Gates | `dsarp/verification/gates.py` | Same | Cheap checks first; only tests accept | [C] |
| Experiment driver | `dsarp/experiments/edge_measure.py` | The 18-move result | Plan, apply, build, judge, patch | [C] |
| Smell identity | `dsarp/experiments/arcan_diff.py` | 37 batches | Matches smells by identity, not count | [C, R] |
| Spoon driver | `tools/dsarp-spoon` | 18 moves applied | Moves a class and rewrites references | [R] |
| OpenRewrite path | `dsarp/openrewrite/runner.py`, `write_move_recipe` | Agreed with Spoon 11 of 12 | Reviewable patches; downstream migration recipe | [R] |
| Merged Arcan | `clever-bassi-39cae2`, uncommitted | log4j2 pass_0 | One Arcan graph across modules; 786 vs 677 findings | [R] |

### Prior work and tools

| Idea or tool | Source | Used in | Our use | Basis |
|---|---|---|---|---|
| Arcan | Arcelli Fontana et al., ICSA-W 2017 | Java smell studies; Pandini used v2.9.4 | Detector oracle | [S, P] |
| ArchUnit `beFreeOfCycles` | ArchUnit guide 1.5.1 | Java test suites | Generated regression rule | [P] |
| Cycle-minimizing search over class moves | Abdeen et al., WCRE 2009 | Package structure case study, on a model | Objective for group search; baseline arm | [S] |
| Dependency-breaking refactorings | Shah thesis, Massey 2013 | Large open-source dataset | Baseline; operators if moves prove insufficient | [S] |
| Cause analysis + refactoring sequence | Kuo et al., IJSI 2024 | One real case | Precedent for explain-then-sequence | [S] |
| Minimum feedback edges | Oyetoyan et al. 2015; Sonargraph | Effort estimation; commercial tool | Edge choice within a group | [S] |
| Re-run detector as judge | SmellBench, arXiv 2605.07001 | scikit-learn agents | Reporting: net delta, false-positive triage | [P] |
| Compile, tests, purity gates | SWE-Refactor, via project status | 703 method refactorings | Confirms gate design | [R] |
| Generated regression oracle | SAFEREFACTOR; EvoSuite, via `TOOLING.md` | Refactoring engine testing | Deferred behavior check | [R] |
| API comparison | japicmp | Maven builds | Report-only binary breaks | [P] |
| LLM two-step edge choice | Pandini, Goknil, Zenodo 19819717 | OpenMRS, CrateDB, ShardingSphere, TeaStore | Deferred baseline arm | [P] |
| Enumerate-and-pick | `TOOLING.md`; MANTRA reviewer shape | LLM refactoring studies | Deferred veto role | [R, S] |
| Tarjan SCC | [U] | Standard | Finds cycle groups | [U] |

Closed, with reason: DistilBERT (macro-F1 0.039), ROSE-style classifiers (no removal measured), package
split (77 of 78 worse), NSGA-III (no use for Pareto fronts here), jQAssistant (adds nothing).

## 3. Build order

Each step has a stop condition. **Do not start a step until the previous one passes.**

### Step 1. Consolidate (Milestone 1)
1. Back up: push `claude/infallible-wescoff-ee351b` and tag it. Your approval needed.
2. Commit `clever-bassi-39cae2` changes onto a new branch from `f82d2ca`, with its test.
3. Diff `ai-agents-refactoring-3afbab` Spoon files against `f82d2ca`; keep only what is missing.
4. Decide on `agent-workflow-breakdown-61430c` (`dd188e8`) separately.
5. Delete stray `tools$d`.

**Done when:** tests pass on one branch, tagged.

### Step 2. Spike (Milestone 2), about one day
Apply `JsonTemplateLayout -> ...layout.template.json.resolver` on Log4j2 through `edge_measure`, one
move, in a copy. Record compile, jdeps, ArchUnit, Arcan, tests, japicmp by hand.

| Outcome | Then |
|---|---|
| Group dissolved, tests pass | Continue to Step 3 |
| Dissolved, tests or API break | Continue; read why; carry into protocol |
| Not dissolved | Diagnose prediction error before any planner work |

**This run is exploratory.** It never counts in the confirmatory result.

### Step 3. Trust the instrument (Milestone 3)
Blocks pre-registration, not the spike.

1. **Known-answer suite** in `tests/known_answers/`: one fixture per past bug: broken build, UD30
   double-count, last-module test totals, red baseline, halted reactor, no-op placebo, dispatch-order change.
2. **Three verdicts** in `gates.py`: PASS, FAIL, INVALID. Skipped module or red baseline gives INVALID.
3. **Test evidence:** `-fae`, surefire XML per module, compare executed test IDs.
4. **Triage 104 cross-module findings** against per-module `jdeps`: real, artifact, or scope.
5. **Freeze graph definition:** one named source per evidence level.
6. **Add `tools/api_runner.py`** (japicmp), report only. `gates.py` advisory, like `before_apply`.
7. **Add dispatch check:** compare `META-INF/services` and service order before and after; a difference is a failure.
8. **Add `experiments/placebo.py`:** neutral edit through whole loop.

**Done when:** every fixture gets its expected verdict, and placebo delta is zero or explained.

### Step 4. Group planner and pilot (Milestone 4)
1. New `dsarp/refactoring/scc_planner.py`: greedy per group using `package_edges_after`, then beam 5 by 4.
   Reuse `move_planner` filters. Reject any plan adding a package to any cycle.
2. Exact-match scoring for the deciding edge: "within two" is too loose for size-2 groups.
3. New `dsarp/experiments/scc_dissolve.py`, one move per copy, re-predict after each.
4. Pilot on repositories outside the confirmatory set: log4j2, pdfbox, tika, commons-validator.
5. Add `archunit_runner` rule emission, only after a real dissolve.

**Decision point.** If pilot dissolves little:
- Inversion or construction blocks most groups: promote service locator and constant inlining.
- Otherwise: report "moves rarely dissolve cycles" as the finding.

### Step 5. Confirmatory run (Milestone 5)
1. Pre-register in `preregistration.json` before first apply: selection rule, weights, K, repositories,
   graph definition, tool hashes, INVALID rule.
2. Use repositories unused so far. Proposed: Struts, Karaf, plus 1-2 unused Apache projects. Tuning data
   from log4j2, pdfbox and tika must not count.
3. Arms: P placebo, C current planner, D group planner, H Abdeen-style annealing. Add A from the ledger.
4. Report funnels with Wilson intervals, by group size, with and without API breaks. INVALID counts as
   not-success, and appears as its own row.
5. Inspect accepted patches; two raters where possible.

**Done when:** numbers published as registered, whatever they say.

## 4. After the result (only if time allows)

EvoSuite on touched types, Shah operators, pre-registered LLM veto, composite extraction with placement
check. Each needs its own justification from Step 5.

## 5. Fix before anyone presents

- `TECHNICAL_REPORT.md` leads with LORO 0.978; that is not the project's result.
- Deck "within one"; the data says within two.
- 18 of 18 means edge removed. Accepted is 14 of 18.
