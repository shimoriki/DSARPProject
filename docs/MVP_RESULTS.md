# DSARP MVP — scope and measured results

DSARP detects architectural smells with real tools, executes refactorings with OpenRewrite,
then re-runs the same tools on the refactored source to verify what was actually removed.

Everything below is a measured tool run. Where a number could not be measured, it says so.

## What is in scope for the MVP

**Five smell types have an automated, compile-safe refactoring:**

| smell | refactoring | recipe |
|---|---|---|
| Cyclic Dependency | Merge Package | `ChangePackage` (stock) |
| Unstable Dependency | Move Class | `ChangeType` (stock) |
| God Component | Split Package | `ChangeType` (stock) |
| Deficient Encapsulation | Encapsulate Field | `ReduceFieldVisibility` (DSARP) |
| Missing / Wide Hierarchy | Introduce Supertype | `IntroduceSupertype` (DSARP) |

Plus `ExtractInterfaceForClass` for Rebellious Hierarchy, and dead-code removal via
`DeleteSourceFiles` when the source index proves zero references.

**Explicitly out of scope, with the reason:**

| smell | why not |
|---|---|
| Insufficient Modularization | needs member-level extraction into a new type — a design judgement about which fields and methods move together |
| Multifaceted Abstraction | same: splitting responsibilities requires deciding what the responsibilities *are* |
| Broken Modularization | needs move-method with real type attribution; DSARP's index is regex-based |
| Broken Hierarchy | replacing inheritance with delegation rewrites the public API and every call site |
| Dense Structure | a property of the whole system; no local refactoring reduces it |

These are reported as `requires_source_inspection` with the reason above — never silently
dropped. Closing them means rebuilding the source index on OpenRewrite's LST so member-level
transformations have type information. That is a rewrite, not an increment.

## How to read the numbers

**Judge a run on the smell types it targeted, not the grand total.** Splitting a God Component
creates a new package, which Designite then reports as Feature Concentration. A refactoring
that removed exactly what it aimed at can therefore make the overall count look worse. The
loop reports `per_type.targeted` (what was aimed at) separately from `per_type.side_effects`
(what moved on its own), and the iterative loop scores only the targeted types.

## First verified smell reduction

On commons-validator, with both tools measuring both sides of a **compiling** build:

```
build_after_refactoring   compiled
verification_status       verified

Arcan       20 -> 13   (-7)
Designite   91 -> 86   (-5)

Unstable Dependency  -7    Cyclic Dependency  -4
God Component        -1    Scattered Functionality  -1
```

Designite's own total FELL. Every earlier strategy made it rise, because splits created
packages it then flagged as Feature Concentration.

What unblocked it was not a new refactoring but an ordering rule. An extracted helper stays
in its origin package and keeps referring to that package's types; a God Component split in
the same pass was relocating those types out from under it. Extract Class now claims its
whole package before a split can take from it. The result is fewer, non-conflicting plans —
28 files changed instead of 50 — and a real reduction rather than churn.

That reframes an earlier conclusion. Three batches showed 1-in-8 and were read as "relocation
is exhausted"; some of that was plans destroying each other's preconditions within a pass.
How much is still being measured.

## Measured results

### commons-validator — `verification_status: verified`, build `compiled`

```
detect      Arcan 20  +  Designite 91   = 111 smells across 13 types
plan        8 applicable plans over 5 smell types, 48 recipe operations
refactor    OpenRewrite composite recipe, 37 files rewritten
re-detect   Arcan 18  +  Designite 94
```

Targeted outcome: **Unstable Dependency 6 → 3**, God Component 3 → 2, Arcan total 20 → 18.
Side effect: Feature Concentration 0 → 3 (the new packages from the God Component split).

### commons-codec — random repo, in no split, cloned by URL

144 smells detected, 1 God Component plan, 14 files rewritten, build compiled, Arcan 23 → 23.
Honest read: the split did not reduce Arcan's count on this repo.

### Repositories

17 cloned. Held out from training: Log4j2 (unseen benchmark), commons-validator.
RefactoringMiner: Spark 777 refactorings (4 architectural), Struts 497 (87 architectural).
The architectural filter is aggressive — most commits are code-level, so architectural label
density is the limiting factor for the learned ranker, not repository count.

## The verification gate

This is the part worth defending. Three times during development a change *looked* like a
large improvement and was actually a measurement failure. Each was caught, and each is now a
permanent guard:

1. **Arcan 20 → 0, "all cycles removed".** The refactored code had not compiled, so there was
   no bytecode and Arcan found nothing. Now: no bytecode ⇒ `smells: null`, `UNMEASURABLE`,
   run marked `unverified_build_broken`. Only tools that measured *both* sides may claim a
   delta.
2. **Iterative loop, "13.2% reduction".** The build broke, Arcan dropped out, and the score
   was silently recomputed over fewer tools. Now: accepting a pass requires
   `build_after_refactoring == "compiled"`, not just `verified`.
3. **LLM proposed deleting a still-referenced class** — while its own reasoning stated the
   class was still referenced. The closed loop returned `verdict: rejected`, "the refactored
   code did not compile". A pre-check now refuses it before it runs.

## AI-proposed recipes

`qwen2.5-coder:3b`, asked about the six smell types DSARP cannot refactor: **0 of 6 usable
proposals.** Two of those failures were harness bugs (a real recipe rejected for omitting its
package prefix; the catalogue listed recipe names without saying what they do, so the model
concluded no recipe could create types when two of them can). Both fixed.

The model declines more often than it proposes — the safe failure mode, but not a useful one.
The harness is model-agnostic (`--model`, `--provider`, `--base-url`), so the open question is
whether capability rather than scaffolding is the limit. If a frontier model also cannot beat
the hand-written strategies, that is a publishable negative result.

## Reproducing

```bash
py -m dsarp.cli refactor-openrewrite --repo apache-commons-validator --detector both
py -m dsarp.cli refactor-iterative   --repo apache-commons-validator --detector both
py scripts/run_ai_recipes.py --repo apache-commons-validator --execute
```

Any repository: `--repo-url <git url>`, or paste it into the dashboard's **Analyze Repo** page.
Tool installation: [SETUP_TOOLS.md](SETUP_TOOLS.md).
