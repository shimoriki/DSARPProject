# Mixed-operator cycle repair

Date: 2026-11-02. Status: design for approval.

Code lives on branch `claude/cycle-repair-loop` (worktree `.claude/worktrees/cycle-repair-loop`).
All paths below are relative to that worktree. This spec sits on the research branch only because
that is where the session ran. Move it with the code when planning starts.

## 1. Intent

Dissolve whole package cycles automatically on real Java systems, with evidence a reader can check.

The current loop can only move classes. Move sets have dissolved 5 of 13 cycles in tuned pilots and
0 of 13 in frozen runs. The seven expert refactorings in the Arcelli Fontana package use two main
operations: 85 class moves and 37 extracted interfaces. This work gives the planner the second
operation inside the same search and the same gates.

## 2. What already exists

This changes the proposal made in chat. Interface extraction is not new.

| Piece | Where | State |
|---|---|---|
| `extractInterface`, `invertEdge` | `tools/dsarp-spoon/.../ApplyEdits.java` | Applies. The consumer owns the interface. Built only from methods the consumer calls |
| Retargeting legality | `TypeConstraints.solve`, `constraintReason` in `ApplyEdits.java` | Works, refuses with reasons |
| Blocker reading | `dsarp/agents/edge_elimination.py:158-171` (`constructed_types`, `dip_removable`) | Reads carriers from the snapshot |
| Group move search | `dsarp/refactoring/scc_planner.py` | Beam over `Dict[class, package]` |
| Loop, freeze, confirm | `dsarp/experiments/scc_dissolve.py` | Works. `_apply` calls Spoon with `moveClass` only |
| Gates | `dsarp/verification/gates.py` | `decide()`; `api` and `before_apply` are advisory |

Measured inversion record, 2026-09-23: 1 of 18 reached acceptance. Refusals were declares nothing of
that type (6), already an interface (4), applied then failed to compile (4), no instance method on
the movable declaration (1), annotation (1), not a class (1). On pdfbox's 380 in-cycle edges, 18% are
unblocked, 67% have a constructed target, 29% declare nothing to retarget. 37% have no operator at all.

Those attempts each aimed one inversion at one edge. Nothing has yet tried inversion and moves
together on one SCC. That is the untested idea here, and it is why the reach probe comes first.

## 3. Goals

1. Predict, before anything is applied, how far a mix of moves and inversions can take each small SCC.
2. Apply a mixed plan as one candidate, through the existing gates.
3. Repair compile failures inside a fixed scope, with an LLM, without letting it change the plan.
4. Report one pre-registered result: dissolved cycles by SCC size, with API breaks beside it.

## 4. Non-goals

- Giant SCCs. Named edges remain the only claim there.
- Hub-Like, God Component, Unstable Dependency.
- Extract helper, parameter object, exception extraction. Later, if the data asks for them.
- Any LLM role in planning, judging or test editing.
- Using the RefAgent repository as code. Only its loop idea is borrowed.

## 5. Anti-goals

The work has failed, even if counts improve, if any of these happen:

- A cycle counts as gone because a dependency became reflective. `ServiceLoader`, `Class.forName` and
  string lookups hide an edge from bytecode without removing it. See the Ant `XalanExecutor` case in
  `dsarp-project-astra/docs/ARCHITECTURAL_REMOVAL_METHODS.md`.
- A repair edits tests, weakens a build rule or skips a gate.
- A shrink or an edge removal is reported as a dissolved cycle.
- Plans change after freezing.

## 6. Decisions

### User's decisions

- Success means whole cycles. Level 4c is the headline; 4a and 4b are reported but do not count.
- Moves of public classes count as success, and each binary break is reported beside it (2026-11-01).
- LLM only as scoped repair, never as planner or judge.

### Author's calls, open to challenge

**D1. Reach probe before any operator work.** It needs no Java changes and no test runs. If it shows
mixed plans do not add dissolvable cycles, the project stops here, before any operator work. Its
cost is compile time plus Spoon model builds across the corpus, not yet measured.

**D2. Consumer-owned interface stays the default placement.** It is already implemented and its
reasoning holds for two packages: `P2.Impl implements P1.Api` adds an edge in the direction that
already exists. In a larger SCC that new edge can sustain another path, so the planner must predict
it rather than assume it. A neutral package is used only if the probe shows it unlocks targets.
This departs from the chat proposal, which made a neutral package the default. A neutral package
is out of this study entirely: `invertEdge` cannot place one, and the probe does not model it.

**D3. Constructed targets stay out of the first version.** A static factory does not help: the
factory must name `P2.Impl`, and `P1` must name the factory, so `P1 -> F -> P2` keeps the path. Only
two things really remove the edge: inject an instance from outside the SCC, or hide it reflectively.
The second is an anti-goal. The first rewrites constructors and callers, so it is out of this study. The
probe reports it as one diagnostic column only, and it never enters an arm. A later study can
take it up. This retracts the chat step that said to keep constructions behind a factory.

**D4. Refuse leaking signatures.** `constraintReason` checks that a type in the interface is
*visible*, not that it is harmless. An interface in `P1` whose method returns `P2.Foo` keeps
`P1 -> P2`. Jackrabbit's `getSessionImpl` is the real example. The planner counts such types as
surviving edges, so the prediction shows the edge stays.

**D5. Repair budget of 5 rounds, files limited to those the plan touched.** RefAgent's rates levelled
off at 12 rounds, but that loop rewrites whole classes. Our failures are narrower, and each round
costs a compile. Raise it only if the data shows late successes.

**D6. Repaired runs are a separate arm.** Deterministic results stay clean, so repair's value is
measurable, including when it is zero.

**D7. Local or API model.** Use the existing model path in `dsarp/refactoring/ai_recipes.py` if it
fits. The record shows `qwen2.5-coder:3b` scored 0 of 6, so do not assume a small local model works.
The builder should confirm a model that can do this before Phase 3, and report its cost.

## 7. Approaches considered

| Approach | Trade-off | Outcome |
|---|---|---|
| Filter moves to predicted-dissolve small SCCs | Cheapest, but leaves the expert operation unused and yields few targets (4 from 9 repos) | Rejected by user as primary route. Its filters are kept here |
| **Mixed moves and inversion, probe first, scoped repair** | Highest chance of new dissolves; reach is unproven and may be small | **Chosen** |
| LLM writes the refactoring (Pandini two-step, RefAgent shape) | Reaches anything; fabrication risk, not reproducible, class-at-a-time cannot do 90 to 261 file changes | Rejected as primary. Survives as bounded repair |
| Non-monotone search (Abdeen annealing, Arm H) | Finds restructurings greedy cannot; more moves and API breaks | Deferred. Experts still did not dissolve cycles this way |

## 8. Design

### 8.1 Planner state

Extend `scc_planner` state from `Dict[class, package]` to a pair: moves, plus a set of inverted
pairs `(consumer_pkg, impl_class)`. `package_edges` applies both. `consumer_pkg` is the package
after that state's moves.

Blockers are stored per class, not per pair, and judged inside the beam for each state. This is
the point of mixing: moving the one class that constructs `Impl` out of `P1` can unblock an
inversion, and a move can also bring a blocker in.

For an inversion of `impl_class` from consumer package `P1`:

- remove class edges from `P1` classes to `impl_class`;
- add `impl_class -> P1` (implements the interface);
- add `P1 -> T` for every type `T` in the kept method signatures (D4).

Only unblocked pairs may enter the search. Blocked means any of: constructed in `P1`, declares nothing
in `P1`, already an interface, annotation, static or field use from `P1`, subclassed in `P1`, generic,
non-public, or in a different source root from `P1`. A pair where only some declarations can be
retargeted (`r.blocked` non-empty) keeps its edge, so it is predicted as not removed. Reuse `edge_elimination` carrier logic where it fits. Blockers needing source facts come
from a cheap read of `SourceFacts`, and Spoon stays the final authority through the existing
dry-run retry in `make_plans`.

The score stays `(cycling packages of comp, packages newly cycling, operations used)`. Plans that pull
in an outside package stay dropped. Beam width 20, depth 4 stay as they are.

### 8.2 Filters at freeze

- `predicted_left == 0`.
- `--max-size 4`, unless the probe argues otherwise.
- Arcan reports the cycle at baseline, otherwise 4c is unreachable.

### 8.3 Applying

`_apply` runs two Spoon passes on the copy: moves first, then inverted pairs on the moved tree,
grouped by consumer and implementation package into `invertEdge` edits with `types`. Inversions
are dry-run on the moved tree too. A partial group from `groupPartition` counts as a refusal of
the plan, because a partly inverted edge survives. `rewrite_names` and residual checks still
cover moved classes.

### 8.4 Scoped repair (Arm R only)

Runs only when the compile fails after a successful apply.

- Input: first javac errors, the touched files, the plan.
- Allowed: edit production files the plan touched.
- Refused without compiling: any change to a test file, build file or anything outside that set; any
  added `Class.forName`, `ServiceLoader` or `@SuppressWarnings`; any changed class-to-package mapping.
- Stop at the budget or on a clean compile. Then all gates run unchanged, with no knowledge of repair.
- Record every prompt, diff, round count and token cost in the row.

### 8.5 Gates and levels

`gates.decide` is unchanged. Add one new hard check, `reflection`: newly added reflective lookups in
changed files fail the candidate. `scc_planner.level` is unchanged. `measure` must store operations
rather than moves in the row, and `success_criterion` is stated before the run.

## 9. Phases and stop rules

**Phase 0, fix known defects.** `rewrite_names` must not edit history files (`RELEASE-NOTES.txt`,
`src/changes/changes.xml`). Diagnose the commons-text case where 34 tests stopped running. Recheck
log4j2 acceptances from `-fae` runs, which skipped modules.

**Repo split, before Phase 1.** Build a pool of Apache Java repos that compile. The repos already
used in pilots or confirmatory runs (pdfbox, tika, commons-validator, log4j2, struts, karaf,
opennlp, commons-collections, maven, guava, csv, email, codec, cli, text, io, lang) are all
Discovery. Split the rest in two by a hash of the repo name, with the hash fixed before any repo
is examined: Discovery and Holdout. The probe and all tuning use Discovery only. Holdout is
touched once, in Phase 4.

**Phase 1, reach probe.** Discovery repos, at least 30 in all, no test runs. It has two stages.

1. Arithmetic screen with every filter in 8.1 and `make_plans`.
2. Spoon dry-run of each surviving plan, on the moved tree for mixed plans. This is existing Java.

An SCC counts as dissolvable only if its plan has `predicted_left == 0` and survives stage 2 with no
refusal and no partial group. Moves-alone plans pass the same two stages, so the comparison is fair.
Report for each SCC of size 4 or less: dissolvable by moves alone, by mix, or neither; whether Arcan
reports it; and, as a diagnostic only, whether dropping the construction blocker would change the result.

Stop rule, fixed now: continue only if the mix adds at least 10 dissolvable Arcan-reported SCCs across
Discovery beyond moves alone. Otherwise report that finding and stop. Repos without a full test
baseline count for this rule, since it measures reach and not acceptance.

**Phase 2, operator in the loop.** Sections 8.1 to 8.3 and 8.5. Exploratory run on pdfbox, tika and
commons-validator. Calibrate prediction error against measured edges.

**Phase 3, scoped repair.** Section 8.4, only if Phase 2 compile failures are a main loss. Otherwise skip.

**Phase 4, confirmatory.** Freeze plans on Holdout repos with a full test baseline, then run with no
changes. If fewer than 20 targets freeze, extend Holdout with new repos by the same hash before any
run. If it is still under 20, report descriptive funnels only and no McNemar.

| Arm | Planner | Repair |
|---|---|---|
| D | Moves only | No |
| M | Moves and inversion | No |
| R | Moves and inversion | Yes, only if Phase 3 ran |
| P | Placebo | No |

Same targets across arms: the union of frozen plans. A target with no plan in an arm counts as a
failure for that arm. Report funnels with Wilson intervals and McNemar on paired targets. No
significance claims across too few systems.

## 10. Evidence and expected outcome

| Claim | Evidence | Strength |
|---|---|---|
| Experts extract interfaces | 37 interfaces, 36 files gaining `implements`, in 7 bundles | Classified by diff and name, not read case by case |
| Experts rarely dissolve | Compress 2 to 2, JeroMQ 1 to 1 | n = 2 |
| API breaks seem inherent | All four evaluated expert variants changed public API | n = 4 |
| Inversion can be safer than a move | Tika `ParseContext`: move broke 37 tests, inversion passed | n = 1 |
| Feedback loops help | RefAgent median tests 44.5% to 90%, single attempt vs loop | Class-level, different problem |

Expected, as judgment: moderate chance Phase 1 passes. If so, low to moderate dissolve rate on small
SCCs, with API breaks on most. No study has shown this working on large Java systems.

## 11. Risks

- **Reach too small.** Inversion is unblocked on 18% of pdfbox edges. Phase 1 exists for this.
- **Consumer-owned interfaces add API.** `P2.Impl` gains a public interface and `P1` signatures
  change, so retyped public methods are binary breaks. Reported, not hidden.
- **Prediction error for inversion is unknown.** Only move arithmetic is calibrated.
- **Design value.** A dissolved cycle can still be a worse design. Sample accepted patches by hand.
- **Snapshot version.** The classification used Zenodo 18754605, not the paper-linked 18754704.

## 12. Left to the builder

File layout inside the existing modules, probe output format, the names in the repo pool, how
signature types reach Python from `SourceFacts` or a Spoon read, and repair prompt wording.
