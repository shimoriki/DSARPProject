# Current Status

## Last updated

2026-07-21 — Completed full MVP + multi-repository generalisation continuation.

## Current objective

DSARP Evidence-Based Refactoring Agent — complete modular platform: local + HPC, multi-repo
training, unseen-repo testing, evidence-grounded no-hallucination suggestions, human HGRS review.

## STANDING PLAN — user granted autonomy to continue (2026-08-05)

User: "once both are done dont wait for my approval begin the next thing to improve the mvp
till it is viable to reliably detect analyse suggest refactor verify retest ie do the whole
loop and remove smells reliably." Continue WITHOUT checking in. Still confirm before anything
outward-facing or destructive (pushing to new remotes, deleting user data, installing software).

TARGET: 4-5 smell types (user directive). Prominence across 37 analysed repos:
  Unutilized Abstraction      4907   most prominent by far
  Unnecessary Abstraction     3599
  Cyclic Dependency           1575   WORKS (-7)
  Deficient Encapsulation     1373   measured 0 effect
  Broken Hierarchy             969
  Unstable Dependency          459   WORKS (-8)
Target set = Cyclic + Unstable (working) + Unutilized + Unnecessary + Deficient Encapsulation.
The first two most prominent are 8500 instances of DEAD CODE, and deletion is inherently
SUBTRACTIVE — unlike splits it cannot create the new packages the detector then flags. That is
the best available route to reliable multi-smell reduction.

**ROOT CAUSE FOUND for why dead-code removal almost never fires**: the findings are dominated
by NESTED classes — DomainValidator.Item, CreditCardValidator.Amex, ModulusTenCheckDigit.* —
and `SourceFacts._file_of` maps FQN -> file by FILE STEM, so `a.b.Outer.Inner` is never
resolved and the plan reports "not found in the source index". On commons-validator that is 8
of 10 refusals; 0 plans were applicable.
TWO pieces of work follow, and they are separate:
  (a) index nested types (walk `Outer.Inner` back to Outer.java) — a correctness fix that
      also unblocks every other strategy operating on nested types;
  (b) a REMOVE NESTED TYPE transformation. DeleteSourceFiles is wrong for a nested class: it
      lives inside its outer file. This needs an LST recipe that drops the member type.
Also check why Deficient Encapsulation measures 0: likely `external_field_users` is so
conservative that almost no field qualifies, so the plan fires but narrows nothing.

BATCH v4 RESULT: 1/8 reduced, totals 4251 -> 4239. Same as v1/v2/v3. FOUR batches now at
1/8. The claim-ordering fix helped validator's single pass (Arcan 20 -> 13) and did NOT
generalise. v5 (outcome ledger active) still running.

DEFICIENT ENCAPSULATION DIAGNOSED (3rd most prominent, 1373 instances): **19 of 23 findings
refuse with "no public/protected instance fields found"** — Designite flags the class but
`SourceFacts.exposed_fields()` matches nothing, so there is nothing to narrow. The 3 plans
that DO fire narrow 16 fields and still measure 0 effect, which fits: the class keeps the 19
fields the regex cannot see, so the smell stays. FIX: make `_FIELD_DECL` match what Designite
matches — check annotated fields, multi-line declarations, and whether Designite counts
`public static` non-final. Verify by comparing the field list against Designite's own
Description text for the same class before changing the regex.

**SMELL DEFINITION MISREAD — Unutilized Abstraction is NOT dead code.** The strategy assumed
"unutilized" meant unreferenced and planned DeleteSourceFiles. With the public-API guard
relaxed (new param `remove_unreferenced_public_types`, safe because we always refactor a COPY)
the refusals resolve to **23 of 32 "still referenced"**. Designite means an abstraction not
used AS an abstraction — an interface/abstract class with no polymorphic use — not one with
zero references. Deletion is therefore the wrong refactoring for the corpus's most prominent
smell (4907 instances). The right one is Collapse Hierarchy / inline the abstraction into its
single implementor. Same class of error as the nested-type bug: the strategy was not looking
at what the detector was actually reporting.
VERIFY THIS FIRST next cycle: read Designite's own Description text for an Unutilized
Abstraction finding and confirm the definition before writing the replacement strategy.

ORDER OF WORK, highest value first:
1. When v4 and v5 land, compare. v4 = all suggestion types; v5 = outcome-ledger active
   (refuses Introduce Supertype / Encapsulate Field / Consolidate Package). Report
   smells_actually_reduced, NOT passes_accepted.
2. Run `--verify-tests` on validator. Every result so far only proves the code COMPILES.
   If the project's own tests fail, existing claims need revising — that is the point.
3. Re-run `scripts/validate_ledger.py` with a different holdout once v5 adds runs. Split
   Package already failed generalisation; check whether Merge Package / Move Class hold.
4. Make a refused refactoring actually work rather than re-enabling it. Introduce Supertype is
   counterproductive because it ADDS a type the detector counts — it must remove something in
   the same move to net out. That is a design change, not a toggle.
5. Wire outcomes.py into scripts/tune_refactoring_params.py, using HELD-OUT agreement as the
   objective, not training-set effect (Split Package is exactly why).

DO NOT: re-enable measured-ineffective suggestions to "cover more smell types". Three batches
plus held-out validation say that reproduces the 1-in-8 pattern.

## RELOCATION IS EXHAUSTED — three controlled batches (2026-08-05)

THE HEADLINE FINDING. Three strategy variants, same result on the same 8 Maven repos:
  v1  apply every applicable plan                                  1/8 reduced
  v2  + budget escalation, patience, best-state guard              1/8 reduced
  v3  + threshold-gated splits, no partial expansive plans         1/8 reduced
Totals across all repos v3: 4274 -> 4264 (0.2%). Four repos ACCEPT passes that compile and
change nothing. Only commons-validator ever reduces. Reports: data/reports/all_repos_v{2,3}.json.
CONCLUSION: moving classes between packages / merging packages REDISTRIBUTES smells; it does
not remove them. No ranking, budgeting, patience or threshold gate changes that. Extract Class
is the only family that removes MEMBERS and therefore the only path to reliable reduction.

METRIC BUG worth remembering: `refactored_and_verified` was defined as passes_accepted > 0 and
reported "5/8 improved" when ONE repo reduced anything. An accepted pass only means it compiled
and was kept. Now `smells_actually_reduced` (after < before) is the headline.

EXTRACT CLASS (dsarp/refactoring/extract_class.py + com.dsarp.recipes.ExtractStaticHelpers):
Python regex surgery NEVER produced compiling Java — 3 defect classes (lost imports, stranded
callers, mangled declarations from regex-qualifying DECLARATIONS not calls). Rewritten as an
OpenRewrite ScanningRecipe on the LST. Progress: regex broke everything -> LST v1 aborted
("Expected to find enclosing SourceFile": printed with a fabricated Cursor(null, m); fix =
print during the SCAN where a real cursor exists) -> LST v2 applied 39 files, scattered errors
-> LST v3 ten errors from two named causes. Cause 2 FIXED (scanner had no class guard, so it
collected every public static method in the REPO). Cause 1 STILL OPEN: imports not resolving in
the generated helper.
PRECONDITION LEARNED (3rd instance of the same pattern): a refactoring's safety depends on
ACCESS, not just structure. `static` only means no `this` dependency — it says nothing about
visibility, so a moved method calling a private helper left behind cannot compile.
See also: package-private constructor blocking subclass moves; package-private types/members
blocking class moves.

HELD-OUT VALIDATION (scripts/validate_ledger.py): 2/3 ledger verdicts held on repos it was
never built from. **Split Package looked effective on training repos and does NOTHING on
unseen ones** — reliable core is TWO refactorings: Merge Package (Cyclic) and Move Class
(Unstable). Fits the earlier evidence: Split Package creates a package the detector then flags.

BEHAVIOUR VERIFICATION added (`run_tests`, CLI `--verify-tests`): runs the repo's OWN test
suite on the refactored copy. Everything before this only proved the code COMPILES, which
cannot detect a behaviour change. NOT yet run on a real repo — do that early, it may
invalidate existing results.

SEVEN measurement artifacts caught by the verification gate this session (Arcan 20->0, iterative
13.2%, both sectioned runs, run-metric 10->18, batch "5/8 improved"). That reliability is the
defensible contribution; the smell-reduction numbers are not yet.

## OPTIMISATION + git-deepen fix + README rewrite (2026-08-04, latest)

**GIT-DEEPEN HANG — ROOT-CAUSED AND FIXED.** `scripts/mine_and_align_refactorings.py` chose
`git fetch --depth=N` (deepen) whenever an existing clone had `1 < cur < depth`. Deepening a
partial clone re-negotiates the whole history and hangs; tika 521->1200 sat SILENT for 20+ min
and produced nothing even though `_git_bounded` had a 600s timeout (the timeout did not save
it). FIX: **never deepen.** `cur >= depth` -> reuse; otherwise `_force_rmtree` + fresh shallow
`git clone --depth N` (already tree-killable and proven — spark cloned fine at depth 400).
VERIFIED: tika now prints "already has 1200 commits (>= 1200); reusing" and git.exe is NOT
running; the only long-running process is java/RefactoringMiner, which is the legitimately slow
BOUNDED step. Distinguish these two when diagnosing: `tasklist` for git.exe vs java.exe.

**PERFORMANCE — SourceFacts is the hot path.** Measured on commons-validator (166 files):
  reference_count         49ms   -> 0.01ms   (~5000x)
  move_blockers           56ms   -> 4.6ms
  siblings_referenced_by  13.2ms -> 1.25ms
  plan_all (91 findings)  10.3s  -> 0.95s    (~11x)
`_scan()` now builds TWO indexes in its single pass: `_mentions` (identifier -> files) and
`_tokens` (file -> identifiers). "Does anything mention X" becomes a set op; remaining regexes
run only against candidates the index cannot decide. Stays FLAT on a 2591-file repo where the
old code cost ~700ms per reference_count. Output byte-identical (84 planned / 8 applicable).
Also: `openrewrite_loop._package_classes` / `_has_subpackages` re-walked and re-read every
.java file on EVERY call -> now backed by a cached SourceFacts (`_FACTS_CACHE`).

**BUG FOUND BY THAT DEDUP:** old `_package_classes` only read the first 2000 chars, so files
with long Apache licence headers were invisible. Reading properly surfaced `package-info.java`
in every package, which made any two packages look like they shared a class -> merge planning
dropped to 0 merges. `SourceFacts._NON_TYPES = ("package-info", "module-info")` excludes them.
Back to the correct 2 merges AND the truncation bug is gone. LESSON: when optimising, diff the
OUTPUT not just the timing — this regression was only caught by comparing merge counts.

README fully rewritten for a first-time reader (loop diagram, then detect/plan/refactor/
re-detect/compare, the 4 compile-safety preconditions, the 3 measurement failures the gate
caught). Old README still called Cassandra the unseen benchmark (it is training) and never
mentioned the closed loop. `docs/MVP_RESULTS.md` + UI page `02_MVP_Results.py` state scope.
Branch feature/arcan-designite-openrewrite-loop pushed; 28 tests pass.

## GIT + iterative loop + SkillOpt parameter surface (2026-08-04, latest)

GIT: repo initialised (was NOT a git repo). Remote https://github.com/shimoriki/DSARPProject,
branch **feature/arcan-designite-openrewrite-loop**, 2 commits pushed (23c9ce4, 36f93b2).
EXCLUDED from git and why: `tools/*` except our own `tools/dsarp-recipes/` — DesigniteJava
Professional is LICENSED COMMERCIAL software and must not be redistributed; also Arcan 144MB,
RefactoringMiner 163MB+150MB zip, Maven 11MB. `DSARP dataset/` (817MB user-supplied raw tool
CSVs + PDFs) and `data/source_index/` (42MB generated). Result: 215 files / 2.8MB.
`docs/SETUP_TOOLS.md` documents installing them. Existing remote branch: agentic-refactoring-agent.

ITERATIVE LOOP `dsarp/verification/iterative_loop.py` + CLI `refactor-iterative` + UI page
`23_Iterative_Loop.py`. Repeats detect->refactor->verify; each pass re-detects on the
REFACTORED code so plans the conflict filter deferred can land later.

TWO BUGS FOUND, both would have produced fake progress:
1. `_apply_and_verify` rmtree'd the refactored copy on exit, so every pass restarted from the
   ORIGINAL source and reported the identical 76->75 four times. Fixed with `keep_copy=True`
   threaded through the single-pass loop.
2. **THE IMPORTANT ONE.** Acceptance used `verification_status == "verified"`, which only
   means SOME tool measured both sides. When the build breaks, Arcan (bytecode) drops out and
   the before/after score is recomputed over FEWER TOOLS — a smaller number that looks like
   improvement but is lost measurement. That scored a broken pass as **13.2% reduction**.
   Acceptance now ALSO requires `build_after_refactoring == "compiled"`.
HONEST RESULT after the fix: commons-validator **76 -> 75 (1.3%)**, 1/2 passes accepted; pass 2
rolled back because its refactoring does not compile. The 13.2% figure was an artifact — do not
quote it. Iteration does NOT currently beat a single pass on this repo; the blocker is that the
second pass's plan breaks the build, not the conflict filter.

SKILLOPT SURFACE `dsarp/refactoring/params.py` (+ `configs/refactoring_params.json`):
god_component_min_classes=6, god_component_min_group=3, unstable_max_crossing=6,
max_package_merges=4, max_class_moves=30, dead_code_max_references=0,
encapsulate_max_external_readers=0, max_passes=5. Strategies now read PARAMS instead of
hardcoded constants. `SEARCH_SPACE` = 576 combinations.
`scripts/tune_refactoring_params.py` — coordinate descent, reward = mean architectural smells
removed, GATE = refactored code must still build (build failure => -inf, rejected with reason).
DELIBERATELY EXCLUDED from SEARCH_SPACE: dead_code_max_references and
encapsulate_max_external_readers — raising either buys score by deleting/hiding code that is
actually used (reward hacking the gate shouldn't have to catch).
NOT YET RUN at scale: needs the 9 training repos to avoid overfitting on 2 repos, and the
pass-2 build failure should be fixed first or the tuner optimises against a broken ceiling.
28 tests pass.

## CUSTOM OpenRewrite recipe module (2026-08-04, latest)

CORRECTION to an earlier claim: stock rewrite-java 8.37.1 DOES contain `ExtractInterface`,
`CreateEmptyJavaClass`, `GenerateGetterAndSetterVisitor`, `ChangeMethodAccessLevel` — so
OpenRewrite CAN synthesise types. BUT `ExtractInterface.CreateInterface` and
`GenerateGetterAndSetterVisitor` are **JavaIsoVisitors, not Recipes**, so they cannot be named
from a declarative rewrite.yml; and there is **no ChangeFieldAccessLevel** at all (verified by
listing the jar). That gap is exactly what a custom module is for.

NEW `tools/dsarp-recipes/` — Maven module (com.dsarp:dsarp-recipes:1.0.0, Java 17,
rewrite-java 8.37.1), built + installed to ~/.m2 with
`mvn -f tools/dsarp-recipes/pom.xml install`. Two recipes:
  * `com.dsarp.recipes.ReduceFieldVisibility` (class, field) — narrows a public/protected
    field to private. Fixes Deficient Encapsulation. No stock equivalent exists.
  * `com.dsarp.recipes.ExtractInterfaceForClass` (class, interface) — wraps the stock
    ExtractInterface visitor as a nameable Recipe. Synthesises a NEW type, so it reaches
    smells relocation cannot (Rebellious Hierarchy, dependency inversion).
Recipes use @Option + @JsonCreator/@JsonProperty (no Lombok) so Jackson can build them from YAML.
`runner.py` appends `-Drewrite.recipeArtifactCoordinates=com.dsarp:dsarp-recipes:1.0.0` when
`custom_recipes_installed()`; `build_custom_recipes()` rebuilds on demand.
Registry: "deficient encapsulation" -> plan_deficient_encapsulation (custom),
"rebellious hierarchy" -> plan_extract_interface (custom). Both evidence-gated:
fields are only narrowed when `external_field_users()==0`.

PROVEN WORKING: a run with all 5 smell types active measured **Deficient Encapsulation 23 -> 22
and Rebellious Hierarchy 2 -> 1** — the custom recipes really do execute and remove smells.

TWO MORE COMPILE-SAFETY GUARDS found from real broken builds:
  3. ExtractInterface copies the class's `extends` clause onto the generated interface ->
     "interface expected here" when the supertype is a class. plan_extract_interface now
     rejects any class with an `extends` clause.
  4. **Pass interference.** Two refactorings touching the SAME type in one OpenRewrite pass
     conflict (extracting an interface from a class another plan relocates leaves the new
     interface in the old package). `_types_touched()` + a `claimed` set: first plan to claim
     a type wins, the other is reported "deferred to the next iteration".

CURRENT VERIFIED STATE — commons-validator, verification_status=verified, build=compiled:
  detect 111 smells / 13 types -> 7 applicable plans over 4 types, 47 operations
  (Cyclic 1, Unstable 1, God Component 3, Deficient Encapsulation 2 custom), 2 deferred by the
  conflict filter -> 37 files rewritten -> Arcan 20 -> 17 (Unstable 6 -> 3); Designite 91 -> 93.
HONEST LIMITATION: the conflict filter makes each pass safe but SINGLE-SHOT — deferred plans
never run, so the per-pass net gain is small. The obvious next step is an ITERATIVE loop
(re-detect and re-plan until no further verified improvement), which would let the deferred
plans land in later passes. Also: splitting a God Component reliably creates a new package that
Designite then flags as Feature Concentration (+3), so Designite can net worse while Arcan improves.
28 tests pass.

## ALL-SMELL refactoring + Designite PROFESSIONAL (2026-08-04, later)

User replaced the community jar with **DesigniteJava Professional 2.9.1**, which finally emits
`ArchitectureSmells.csv` (Project,Package,Smell,Description) + `DesignSmells.csv` +
Implementation/Testability/TestSmells. On validator: 4 ARCHITECTURE smells (God Component 3,
Unstable Dependency 3, Cyclic Dependency 3, Scattered Functionality 1) + 10 design smell types.

**PRO GOTCHA (cost 2 debug cycles):** Pro REFUSES to run when the output folder is non-empty
("The specified output folder is not empty. Quitting..") and exits non-zero. Stale community-edition
CSVs silently blocked EVERY Pro run -> Designite reported `None`/unmeasurable on both sides.
`run_designite` now `shutil.rmtree`s the out_dir first and detects that message explicitly.
`run_arcan` got the same clean-first treatment so a previous run's CSVs can never be re-parsed.

NEW `dsarp/refactoring/strategies.py` — a strategy REGISTRY so refactoring is no longer
cyclic-only. Each strategy turns one tool finding into stock OpenRewrite recipe entries, or
returns `applicable=False` WITH an evidence-backed reason (never a silent skip):
  God Component          -> Split Package    (group classes by trailing name stem, move the
                            largest cohesive group into a NEW sub-package = no name collisions)
  Scattered Functionality-> Consolidate Package (pull the same concern back into one package)
  Unstable Dependency    -> Move Class       (relocate the few classes creating the bad edge)
  Unutilized/Unnecessary Abstraction -> Remove Dead Code (`org.openrewrite.DeleteSourceFiles`,
                            ONLY when reference_count==0 AND not public API AND not test code)
  Cyclic Dependency      -> Merge Package (ChangePackage; owned by the loop, unchanged)
  Insufficient Modularization / Deficient Encapsulation / Broken|Wide|Missing|Rebellious
  Hierarchy / Broken Modularization / Multifaceted Abstraction / Dense Structure ->
                            documented NOT automatable, each with the specific reason (they all
                            need a NEW type or member-level rewrite; no stock recipe synthesises
                            types). Reported as requires_source_inspection.
Designite names only ONE package per architecture smell; the peer packages are in the
Description prose -> `_related_from_description()` parses "…component(s): a.b; a.c" so Unstable
Dependency / Scattered Functionality plan against the TOOL'S OWN evidence, not a guess.
The loop composes ONE rewrite.yml from all strategies (`write_composite_recipe`) and runs it once.

THREE COMPILE-SAFETY PRECONDITIONS discovered the hard way (each was a real broken build):
1. **Stranded siblings.** A moved class referenced same-package types with no import. Fix:
   `Plan.pre_imports` + `apply_pre_imports()` writes the explicit imports into the COPY before
   the recipe runs. NOTE: OpenRewrite's `AddImport` CANNOT do this — with `onlyIfReferenced` it
   inspects the file while it is still in the old package, sees the sibling as accessible, and
   adds nothing. (Verified empirically: 0 AddImport effects.)
2. **Package-private access.** `Constants` (package-private type) and `Validator.toLocale()`
   (package-private method) are unreachable once a class leaves the package, and NO import can
   fix it — widening visibility would change the public API. `SourceFacts.move_blockers()` now
   detects both and drops those moves (God Component: 1 of 7 movable in validator's root pkg).
3. **Test code is never refactored** — Designite reports smells on test classes, and a
   zero-reference count on a test proves nothing (the runner invokes it).
Two regex bugs fixed while building the guard: `new Foo(` was parsed as a package-private member
declaration (blocked nearly every move), and truncating the file at the first `{` landed inside
the Apache licence header so every public type looked package-private.

VERIFIED RESULT — commons-validator, `verification_status: verified`, build after = **compiled**:
  detect     Arcan 20 + Designite 91 = 111 smells across 13 types
  plan       6 applicable plans over 3/13 smell types, 34 recipe operations
             (Cyclic 1, Unstable Dependency 2, God Component 3); 83 findings reported
             not-automatable with reasons
  refactor   OpenRewrite composite recipe, 36 files rewritten
  re-detect  Arcan 17 + Designite 93
  compare    **Arcan 20 -> 17 (Unstable Dependency 6 -> 3)**; Designite 91 -> 93
             (God Component -1, but Feature Concentration +3 appeared — splitting a God
             Component creates a new package that Designite then flags. HONEST trade-off,
             both sides measured.)
28 tests pass.

DASHBOARD: `22_Real_Tool_Loop.py` gained a **smell-type coverage table** (every detected type ->
refactored / not automatable + the reason) and a per-plan breakdown in the plan step.

## ARCAN RUNS + fully VERIFIED closed loop, both tools (2026-08-04)

User supplied the FULL Arcan distribution: `tools/arcan-1.2.1/distribution/arcan-1.2.1/`
(jar + lib/ 121 jars). The bare jar is thin and still unusable — `arcan_home()` requires a
jar sitting next to a NON-EMPTY lib/, which is what makes the difference.

ARCAN CONTRACT (1.2.1): `java -jar arcan-1.2.1.jar -p <folder> -out <dir> -all`.
**It analyses COMPILED BYTECODE, not .java source** -> every run is `mvn compile` first, then
Arcan on target/classes. New module `dsarp/tools/arcan_runner.py` (compile_repo / run_arcan /
detect_with_arcan, multi-module aware).
OUTPUT SCHEMA SURPRISE: 1.2.1 does NOT write smell-characteristics.csv. It writes
`packageCyclicDependencyTable.csv` + `classCyclicDependencyTable.csv` (MEMBERSHIP MATRIX:
row=Cycle0..N, column=component, cell 1 = member), plus `UD.csv`/`UD30.csv` (unstable),
`HL.csv` (hub-like, only if any), `PM.csv`/`CM.csv` (metrics). Added `ArcanAdapter.parse_arcan_1_2`
+ `_parse_cycle_matrix`/`_parse_ud`/`_parse_hl`, and directory dispatch that auto-detects the
schema. JDK/third-party nodes (java.*, javax.*, org.xml.sax…) are filtered from cycle members.

`--detector both` runs Arcan AND Designite before and after; findings tagged by tool, `by_tool`
keeps them separable. CLI: `refactor-openrewrite --repo|--repo-url --detector {arcan,designite,both}
--strategy {merge_package,move_classes}`.

TWO REAL BUGS FOUND AND FIXED (both would have produced fake results):
1. **False clean bill of health.** First both-run reported Arcan 20 -> 0 = "all cycles removed".
   FALSE: the refactored copy did not compile, so there was no bytecode and Arcan found nothing.
   Now `measured` is tracked per tool; no bytecode => `smells: None` + UNMEASURABLE, and
   `verification_status = unverified_build_broken`. Only tools that measured BOTH sides may
   claim a delta. NEVER report a failed build as smells removed.
2. **Contradictory recipes.** `dict.fromkeys` deduped (old,new) PAIRS, so the same class could be
   assigned two different destinations (X -> a.X and X -> b.X) from overlapping cycles ->
   160 compile errors. `_dedupe_moves` now enforces ONE destination per class.

STRATEGY CHANGE (the key insight): per-class `ChangeType` moves break the build, because a class
moved out of its package loses the implicit same-package references it never had to import
("cannot find symbol AbstractCheckDigit"). New DEFAULT `merge_package` uses OpenRewrite
**ChangePackage** to relocate WHOLE packages — every class moves together so intra-package refs
survive, and deleting a package removes every cycle through it. Two hard guards in
`_merge_is_safe`: (a) simple-name COLLISION (validator.ISBNValidator vs
validator.routines.ISBNValidator both exist -> merge rejected); (b) src has SUB-PACKAGES
(ChangePackage rewrites the whole prefix -> descendants dangle).

VERIFIED RESULT — commons-validator, `verification_status: verified`, build after = compiled:
  detect     Arcan 20 (14 Cyclic Dependency + 6 Unstable) + Designite 165 = 185
  plan       2 safe package merges (checkdigit -> validator, util -> validator)
  refactor   OpenRewrite ChangePackage, BUILD SUCCESS, 20 files rewritten
  re-detect  Arcan 16 + Designite 167
  compare    **Arcan 20 -> 16 (-4: Unstable Dependency 6 -> 1, Cyclic 14 -> 15 +1)**;
             Designite 165 -> 167 (+2). Honest mixed result, fully measured on both ends.

RANDOM-REPO TEST (apache/commons-codec, in NO split — clone by URL worked end-to-end):
  Arcan 23 + Designite 171 = 194 smells detected. Then **0 moves** — and the system now EXPLAINS
  why via `explain_no_moves()`: commons-codec has ZERO package cycles; all 35 cyclic smells are
  class cycles INSIDE one package, which no package relocation can dissolve (needs dependency
  inversion / extract-interface, no stock OpenRewrite recipe). Reported as
  `verification_status: not_applicable_no_safe_refactoring` + `requires_source_inspection`
  rather than silently doing nothing.

DASHBOARD: new `01_How_It_Works.py` (live tool-availability table, the 5-step loop, both
strategies + guards, the honesty rules) and `22_Real_Tool_Loop.py` (before/after per tool and per
smell type, bar chart, every step with its real command status, unverified/not-applicable banners).
`00_Analyze_Repo.py` gained a "run the REAL tool loop" checkbox + detector picker for any git URL.
SHOWCASE.BAT rewritten: 7 steps, UNSEEN repo is now **Log4j2** (was Cassandra — Cassandra is
training-only now); step 6 is the real Arcan+Designite -> OpenRewrite -> re-detect loop; the
stale hardcoded "cassandra excluded" leakage message now prints the ACTUAL split from SplitManager.
28 tests pass.

## REAL OpenRewrite closed loop EXECUTED + verified (2026-08-03)

The full real tool loop now RUNS end-to-end on commons-validator (`refactor-openrewrite --repo
apache-commons-validator`, `dsarp/verification/openrewrite_loop.py`):
  1 detect  DesigniteJava           -> 165 smells (18 Cyclic-Dependent Modularization)
  2 plan    DSARP                    -> 16 concrete class moves (ChangeType, from cyclic boundaries)
  3 refactor OpenRewrite mvn rewrite:run -> **BUILD SUCCESS, 41 real .java files rewritten**
  4 re-detect DesigniteJava (on refactored copy) -> 148 smells
  5 compare                          -> **17 smells removed** (165->148)
This is REAL: OpenRewrite relocated classes + rewrote imports/refs; Designite re-ran on the changed
source. Not simulation. `openrewrite_loop_report.json` written; changed_files (41) patched in.

KEY HONEST FINDING (the deep point): the 17 removed were Broken Hierarchy -6, Unutilized Abstraction
-10, Deficient Encapsulation -1, Wide Hierarchy -1 (Missing Hierarchy +1). **Cyclic-Dependent
Modularization delta = 0** (stayed 18). WHY: `ChangeType` RELOCATES a class but keeps its
bidirectional type refs, so a package move does NOT dissolve a type-to-type cycle. Breaking a cyclic
smell needs a DEPENDENCY-BREAKING refactoring (Extract Interface + Dependency Inversion — move the
shared contract to a new abstraction both sides depend on), which OpenRewrite has no auto-seam recipe
for. So ChangeType is right for God-Component/package smells, wrong for cyclic. Next layer if pursued:
generate an Extract-Interface recipe (new interface type + ChangeType refs to it) at the cycle seam.

FIXES this turn: run_recipe cmd now passes `-Drewrite.configLocation=<abs>/rewrite.yml` (was "Recipe
not found") + build-audit skips (`-Drat.skip` etc., apache-rat was rejecting rewrite.yml); changed_files
regex now matches OpenRewrite's real log line `Changes have been made to <file> by:`. Arcan JAR
(tools/arcan-1.2.1.jar) still UNRUNNABLE (thin jar, NoClassDefFoundError tinkerpop/gremlin — needs full
dist w/ lib/). Designite community edition writes designCodeSmells.csv only (no ArchitectureSmells.csv).

## Completed (this continuation, Tasks 1-20 + multi-repo addendum)

- **Gap report** `docs/IMPLEMENTATION_GAP_REPORT.md`.
- **SQLite backend** `dsarp/db/` (models/database/migrations/repositories/importer);
  CLI `db init|status|import-outputs`. UI/API read DB or files.
- **Source index** `dsarp/source_index/` — regex Java indexer → files/classes/methods/packages +
  import edges; wired into validators (real entity existence, else requires_source_inspection).
- **Graph** upgrades: instability metric, `slice_around`, `edges_hash` for revision cache.
- **Multi-repo core**: `dsarp/splits/` (SplitManager, leakage guard, LORO folds),
  `dsarp/features/` (23 repo-independent structural features + NameMasker Component_A/B/C),
  `dsarp/dataset/multi_repo.py`, `dsarp/training/ranker_trainer.py` (LORO, feature importance,
  overfitting warning, versioned metadata), `dsarp/training/lora.py` (guarded).
- **Execute mode**: `dsarp/tools/runner.py`; Arcan/Designite/RefactoringMiner run configured
  JVM commands, record status/logs, emit NO evidence on failure (no fabrication).
- **Unseen inference** `dsarp/inference/unseen.py` — build detection + tool fallback + transparency.
- **Generalisation report** `dsarp/reporting/generalisation.py` (md/json/csv).
- **Insights** `dsarp/insights/` (8 features). **OpenRewrite validation** `dsarp/openrewrite/validator.py`.
- **Model UX** `dsarp/models/manager.py` (list/smoke-test/--model). **FastAPI** `dsarp/api/` (11 endpoints).
- **Demos** `dsarp/demo.py` (`demo full`, `demo plan|submit`). **Comprehensive CLI rewrite** `dsarp/cli.py`.
- **UI**: 20 pages (added Multi-Repo Training, Repository Splits, LORO, Unseen Evaluation,
  Generalisation, Insights, Token Optimisation, HPC Monitor; upgraded Suggestions with evidence
  cards, no-hallucination panel, why-this-rank, recipe risk, graph delta, comparison, issue draft).
- **Slurm** (parameterised): serve_vllm, mine_all_repos, train_ranker, train_lora_optional,
  evaluate_cassandra, full_pipeline_hpc (+ legacy).
- **Docs/examples**: api_contract.md, inter_agent_protocol.md, GENERALISATION_REPORT.md,
  FINAL_MVP_STATUS.md, examples/*.example.json.
- **Schemas reconciled**: hgrs_review_schema + context_package_schema aligned to implemented models.

## Verified (offline, `py` 3.13.5)

- `pytest -q` = **23 passing**; compileall dsarp/ui/scripts OK.
- `demo full` end-to-end: 32-example multi-repo dataset (4 repos), sklearn ranker, LORO mean 1.0,
  16 Cassandra suggestions grounding_pass=1.0 hallucinations=0, 78k tokens saved.
- `evaluate --name mini-java --model offline`: unseen local Java repo → cycle smell found,
  build_system=plain-java, graph_source=source-index-imports, tools_unavailable reported.
- FastAPI: GET /projects, /suggestions, /reports/cassandra all 200.
- Leakage guard caught a real config bug (commons-collections in train+test) and blocks Cassandra.
- Ollama (`qwen2.5-coder:3b`) still works; cache re-run 16/16 hits.

## Environment

`py` (3.13.5). Installed: pydantic, PyYAML, networkx, jsonschema, pytest, requests, scikit-learn,
streamlit, pyvis, fastapi, uvicorn. Ollama running with qwen2.5-coder:3b.

## Bounded-RM large training — DONE (2026-07-23)

FINAL: 11 real repos (ALL training repos, Cassandra excluded), **5022 rows / 1603 positives**,
sklearn.GradientBoosting, train_score=0.9918, **LORO=0.9535** (worst folds commons-cli 0.833,
commons-io 0.909). Deployed 11-repo ranker active in inference (Extract Interface learned=0.999 vs
Move Method 0.566). Feature importance now diverse (catalogue_rank, severity, centrality, risk).
REAL RM architectural labels from 9 repos: commons x4, tika(557 arch), log4j2, struts(87), maven(493),
spring-framework(235 arch, RM completed at 300 commits, 485s). guava + lucene = STRUCTURAL-only
(RM timed out at 900s -> 0 architectural events, but structural smells gave rows via weak labels).
25 tests pass.

KNOWN ISSUE: apache-lucene step took 27913s (~7.75hr!) — the clone/processing timeout was ESCAPED
(likely orphaned git child procs on Windows and/or pathological graph-metric compute on the huge
partial clone). This is what advanced the wall clock ~a day. guava was bounded fine (2072s = clone
1200 + RM 900). FIX NEEDED: kill the whole process tree on subprocess timeout + guard graph metrics
on very large graphs. For giants, prefer smaller --max-commits and skip if clone exceeds cap.

## Bounded-RM large training (2026-07-22, in progress)

Big-repo RM is too slow on the whole branch (log4j2 1242 commits >15min). FIX: added
`--max-commits N` -> RM `-bc HEAD~N HEAD` (bounds commits). log4j2 last-300 = 172s (was >15min).
Also fixed: read_json resilient to corrupt/truncated json; RM writes atomic (tmp+rename, no
corrupt cache on kill); Windows-safe `_force_rmtree` (clears read-only .git packs) for fresh clones;
per-repo clone-timeout. Ran `--depth 400 --max-commits 300 --skip-mine --train` on 11 repos.
Completed with real architectural labels: commons-cli/lang/io/collections, tika, log4j2, struts
(87 arch, 530 rows), maven (493 arch, 582 rows, 729s); guava mining; lucene+spring queued (giants).
~2760+ rows across 8+ repos so far. Will retrain full set on completion. Deployed model before this
run: 5 repos/1091. NOTE: several long BACKGROUND jobs earlier reported "completed exit 0" prematurely
(launcher-shell / harness quirk) — always verify via processes + output file, not just the notification.

## All-smell verification + before/after graph + Maven (2026-07-29, later)

- FIXED "only cyclic": `verify_suggestion` is now smell-type-generic. Snapshot carries `findings`
  (type+components) + `has_smell()`. Routing: Cyclic->Move Class/break_cycle (source); God Component
  /Hub-Like->`apply_split_package` (move half the classes to <pkg>.internal, source); Unstable->graph
  sim; Feature Concentration/Scattered/Dense (Arcan/Designite-only) -> HONESTLY marked "cannot verify
  without re-running the tool" (structural detector can't re-detect them). smell_removed metric is
  per-type: cyclic=cycle_count reduced; god/hub=specific smell gone. validator now 6/8 removed.
- So most refactorings are REAL source changes (move files + rewrite package/imports), NOT graph
  simulation — only Unstable uses sim; Arcan-only are unverifiable-without-tool.
- BEFORE/AFTER dependency graph: e2e step 9 + data/outputs/<repo>/graph_before_after.json (edges +
  metrics before vs after removing broken edges). UI `00_Analyze_Repo.py` renders metrics + two pyvis
  slices (before: broken edges red; after: gone). validator: edges 43->39, pkgs-in-cycles 4->0.
- BUGFIXES: pip install pyvis (was missing); removed invalid `scrolling=` kwarg from st.iframe in
  05_Dependency_Graphs.py (was crashing).
- MAVEN: downloaded tools/apache-maven-3.9.9 (works). Attempted real `mvn rewrite:dryRun` on validator
  -> genuinely runs but dependency download is ~9kB/s (slow net), didn't reach recipe in-session; also
  Java 26 may be too new for OpenRewrite. `_has_maven()` now finds the bundled Maven.
- HONEST LIMITS: no Arcan JAR -> can't re-run Arcan after refactoring (use structural detector, same
  smell defs); OpenRewrite stock recipes can't do break-cycle/split-package (not recipes) -> the
  deterministic applier does the equivalent + we generate ChangeType recipe artifacts. 28 tests pass.

## END-TO-END pipeline + git-URL UI + dashboard cleanup (2026-07-29)

- Log4j2 -> UNSEEN (repos_unseen.yaml); validator -> secondary test; cassandra stays training-only.
- `dsarp/e2e.py` `run_pipeline()` + CLI `dsarp-local pipeline --repo <n> | --repo-url <url>`: records a
  result at EVERY step: 1 acquire 2 detect (Arcan imported output if present, else structural detector)
  3 graph 4 suggest ALL smell types 5 OpenRewrite recipes 6 apply+recheck (per-suggestion) 7 re-detect
  cumulative 8 verdict. Saves data/outputs/<repo>/e2e_report.json.
- Honest tooling: NO Arcan JAR + NO Maven locally -> can't execute Arcan/OpenRewrite fresh. Uses
  imported Arcan smells (log4j2 711) for detection + structural detector for re-detection (same smell
  defs) + deterministic applier (== OpenRewrite move/change) for apply; recipes generated as drafts.
  Execute-mode wired for when binaries exist.
- RESULTS: log4j2 (unseen): 1026 smells/7 types (711 Arcan), 1073 suggestions/6 types, 2000 cycles,
  cumulative 67->58 pkgs freed (13.4%), irreducible 46-pkg core. validator: 5 smells, 8/8 removed,
  4->0 cycles FULLY UNTANGLED.
- Perf: forced OFFLINE explainer in e2e (log4j2 has 100s of smells -> Ollama was the bottleneck);
  verify_suggestion now takes precomputed before-snapshot + source_index (reuse, not re-index N times).
  log4j2 still ~5min (1500 files, copies for Move Class verify); validator ~30s.
- NEW UI page `00_Analyze_Repo.py`: paste git URL -> runs run_pipeline -> shows each step (detect chart,
  suggestion table, recipes, per-suggestion effect, cumulative metrics). Home page simplified.
- DASHBOARD CLEANUP: 21 -> 8 pages. Archived to ui/_archive_pages/: Projects, Repository_Mining,
  RefactoringMiner_Events, Training_Dataset, Model_and_Ranker_Training, Cassandra_Evaluation,
  Multi_Repo_Training, Repository_Splits, LORO_Validation, Unseen_Evaluation, Generalisation_Report,
  Insights, Token_Optimisation, HPC_Job_Monitor. Kept: Analyze_Repo, Tool_Evidence, Dependency_Graphs,
  Suggestions, OpenRewrite_Recipes, Human_Review, Reports, Refactoring_Verification. 28 tests pass.

## EXPERIMENT: Cassandra-in-training, Log4j2 fixed test (2026-07-29)

User reversed the unseen invariant: Cassandra too big to test on -> TRAIN on it; Log4j2 = fixed
held-out TEST; commons-validator = random unseen test. Changes: repos_train.yaml (+cassandra,
-log4j2), repos_test.yaml (log4j2), repos_unseen.yaml (commons-validator); SplitManager
BLOCKED_IN_TRAINING=() and is_training_allowed also excludes `test` repos (defence in depth).
Shallow-cloned Cassandra (~large). `scripts/build_experiment_dataset.py`: keep still-trainable
RM rows (drop log4j2's 5277), + Cassandra weak-labelled (12439 smells -> capped 400 -> 2398 rows,
no RM - too big to mine). Dataset = 5846 rows / 6 repos incl. Cassandra. GBM LORO 0.8604 ->
**neural LORO 0.9551 DEPLOYED** (trained ON cassandra, holds out log4j2). Grokking not detected.
NOTE: dataset lost tika/maven/spring/guava when last turn's deeper-mine truncated the file pre-outage;
restore via a full `--skip-mine` rebuild for a fuller experiment.

TESTING UPGRADE: every suggestion now gets a MEASURED verdict. Move Class = source-applied on a
repo copy; design-heavy (Extract Interface / Dependency Inversion / Facade) = GRAPH-SIMULATED (remove
the target boundary edge, re-count cycles) via `simulate_refactoring()`. Fixed a real measurement bug:
snapshot used the DISPLAY-capped cycles list (50) not the TRUE `cycle_count` (up to 2000) -> added
`SmellSnapshot.cycle_count` and use it for all before/after comparisons.
CORRECTED closed-loop results:
  mini-java (1 cycle)             -> Move Class 1->0  REMOVED (source)
  commons-cli (1 cycle)           -> Move Class 1->0  REMOVED (3 crossing classes, source)
  commons-validator (4 cyc, RANDOM test) -> Extract Interface/Dep Inversion 4->3, **6/6 would remove** (sim)
  log4j2 (2000+ cyc, FIXED test)  -> 0/8, single-edge break has no effect on a massive tangle (honest)
FINDING: on tractable repos the system's #1 recommendations DO remove smells (validated by source-apply
AND graph-sim); log4j2's core is a pathological 2000+-cycle tangle no single refactoring dents.
CLI: `verify-effect --appliable-only`. 28 tests pass (updated leakage tests).

CUMULATIVE multi-step testing (`verify-effect --cumulative`): applies top-N suggestions together,
tracks the cycle-reduction trajectory. Uses SCC metrics (largest tangle + #packages-in-cycles) —
linear-time + uncapped, unlike raw simple_cycles which saturates at 2000 on dense graphs.
  validator (RANDOM test): top-4 suggestions -> packages-in-cycles 4->0 (100% freed) FULLY UNTANGLED.
  log4j2 (FIXED test): top-35 -> pkgs-in-cycles 67->58 (9 freed, 13.4%); core tangle SCC 48->46 pkgs.
FINDING (quantified): the system's #1 suggestions FULLY resolve tractable repos; log4j2 has an
irreducible ~48-package strongly-connected CORE that boundary refactorings can't break -> needs deep
restructuring. `simulate_cumulative()` in effect_checker; verify_cumulative.json saved. 28 tests pass.

VISION (user): push ANY repo -> SEPARATE AGENTS (goose-style) detect smells + graphs -> suggest ->
OpenRewrite recipes -> recheck removed. Closed loop EXISTS (verify-effect); multi-agent orchestration
+ real OpenRewrite/Maven execution are the next layer. "keep log4j as testing" (done).

## Closed-loop refactoring-effect verification — DONE (2026-07-29)

`dsarp/verification/effect_checker.py` + CLI `dsarp-local verify-effect --repo <name> [--path]`.
Loop: snapshot smells (SourceIndexer+graph+StructuralSmellDetector) -> APPLY refactoring on a repo
COPY -> re-index -> re-measure -> diff. Objective (graph defines cyclic/hub/unstable smells).
- `apply_move_class`: deterministic move (relocate file, rewrite package decl, update imports/FQNs
  across repo, excl. /test/). `apply_break_cycle`: moves ALL classes creating the cheaper edge
  direction of a 2-cycle. `write_openrewrite_recipe`: emits equivalent OpenRewrite ChangeType YAML.
- Move Class is auto-appliable; design-heavy (Extract Interface, Dependency Inversion, Facade,
  Adapter, Move Method) => plan-only, honestly reported "not auto-appliable".
- DEMOS: mini-java (single move -> cycle 1->0). REAL apache-commons-cli (single move INSUFFICIENT on
  real multi-class cycle -> escalates to move 3 crossing help->cli classes -> cycle 1->0 SMELL REMOVED).
  OpenRewrite recipe generated per success. 28 tests pass (+3 effect tests).
- OpenRewrite NOTE: Maven NOT installed -> can't run `mvn rewrite:run`; deterministic applier does the
  equivalent transformation; recipe saved as artifact. Arcan/Designite recheck uses graph detector
  (self-contained); real Arcan/Designite recheck needs the JARs (execute-mode wired).
- Full loop on ANY new repo: `dsarp-local evaluate --repo-url <url> --name X` then `verify-effect --repo X`.
- TODO/secondary (user "can also try"): Cassandra-for-training + new-repo-as-test = swap split configs +
  relax SplitManager.BLOCKED_IN_TRAINING ('cassandra' hardcoded); reverses the unseen benchmark (offer).

## Enriched neural ranker + efficiency + streamlit fix (2026-07-29)

- Neural sweep on 13k enriched rows was pathologically slow (full-batch, 800ep when it converges
  by ep3, per-epoch eval on full 13k). FIXED neural_ranker.py: MINI-BATCH SGD (batch 512), cheap
  eval (2000-row train probe), relative grokking threshold. Now ~5min not ~100min.
- Retrained on 13k enriched: **neural LORO 0.9409 > GBM 0.9179 -> neural DEPLOYED** (9 repos, 13243 ex).
  Progression: 5k structural (GBM .9535/neural .9779) -> 13k tool-enriched, harder (GBM .9179/neural .9409).
- Fixed Streamlit deprecation in ui/pages/05_Dependency_Graphs.py: `st.components.v1.html` (removed
  after 2026-06-01) -> `st.iframe` with a base64 data URI for the pyvis graph.
- Deeper re-mine (depth 1500) RESULTS: MIXED. Improved: commons-cli (arch 41->52, 1075->3486 refs),
  commons-io (117->191, 601->4478). FAILED (kept old data via atomic write): log4j2 (rc=124 RM timeout
  AND ~7hr git-deepen runaway), struts (rc=124), commons-collections & lang (rc=1 RM error).
- ROOT-CAUSE FIX (scripts/mine_and_align_refactorings.py): added `_git_bounded()` — Popen + taskkill
  /F /T on timeout for git clone AND deepen. The 7hr hang was `subprocess.run(timeout=600)` blocking in
  post-timeout communicate() while orphaned git-index-pack held the inherited pipe. NOT yet compile-tested
  (compute classifier was down when made) — verify with `py -m compileall scripts` when back.
- Deployed ranker UNCHANGED (deep-mine ran without --train): still neural 0.9409 (9 repos, 13243 ex).
  Dataset file real_labeled_candidates.jsonl is currently TRUNCATED to 6 repos (8725 rows).
- PENDING (blocked on compute classifier being down 2026-07-29): (1) `py scripts/mine_and_align_refactorings.py
  --repos <all 9> --skip-mine --train` to restore full dataset w/ deeper cli/io + tool evidence;
  (2) `py scripts/train_neural_ranker.py --epochs 150 --deploy` to retrain+redeploy neural. Then report LORO.
- 25 tests pass (as of before classifier outage).

## Real Arcan + Designite integration (2026-07-25)

The user's `DSARP dataset/` has REAL Arcan + Designite outputs for 5 repos: Tika, Struts,
Logging-Log4j2, Karaf (validation), Cassandra (UNSEEN). Now INTEGRATED:
- Upgraded `tools/arcan.py` to parse real `smell-characteristics.csv` (smellType, AffectedElements
  bracket-list, Severity, ATDI). Designite adapter already parsed `ArchitectureSmells.csv` (Project,
  Package,Smell,Description). New script `scripts/import_arcan_designite.py` globs per-module
  subfolders (Karaf/{jaas,jdbc,jms,Main}_Output, cassandra/{cql3,db,tools}_Output) and writes
  data/raw/{arcan,designite}/<canonical_pid>.json.
- Imported: tika A278/D261, struts A292/D293, logging-log4j2 A717/D450, karaf A67/D17,
  cassandra A12154/D105 (UNSEEN - eval only, blocked from training by guard).
- prepare_evidence now MERGES tool smells: Tika 34 -> 567 smells (44 confirmed by >=2 sources:
  Arcan+Designite+StructuralAnalysis). Added Designite smell types to candidate CATALOGUE
  (Feature Concentration, Scattered Functionality, Dense Structure). Removed stale synthetic tool
  files (apache-log4j2, google-guava). Fixed config pid apache-log4j2 -> apache-logging-log4j2.
- Rebuilt dataset with `mine_and_align --skip-mine`: **5022 -> 13243 rows** (log4j2 1028 smells/5283
  rows, tika 572/2647, struts 570/2691). **GBM LORO dropped 0.9535 -> 0.9179** (HONEST: real tool
  smells make it a harder, more realistic problem). Neural ranker retraining in background on 13k rows.
- NOTE: user is actively editing `scripts/mine_and_align_refactorings.py` (added atomic tmp write +
  rename, `--max-commits` -bc bounding, safe rmtree). Do NOT clobber. Process-tree-kill on timeout
  still a TODO (orphaned git/JVM), but max-commits bounding reduces the risk.
- TODO (user ask): increase refactoring history depth — log4j2 has only 17 architectural refactorings
  at depth 500; re-mine deeper / higher --max-commits for low-count repos.

## Grokking-informed neural ranker — DONE, BEST MODEL (2026-07-23)

`dsarp/training/neural_ranker.py` (torch train, torch-FREE numpy inference `NumpyMLP`) +
`scripts/train_neural_ranker.py` + `scripts/sweep_neural_ranker.py` + CLI `dsarp-local train neural`.
Small MLP (64,32), AdamW weight_decay=0.01, up to 3000 epochs, REPO-level held-out tracking
(grokking curve) + best-held-out checkpoint. On the 11-repo real dataset (5022 rows):
**neural LORO=0.9779 vs GBM 0.9535** -> neural DEPLOYED (backend neural-mlp-grokking).
Discriminates well (Extract Interface 0.94 vs Introduce Facade 0.11). Inference is pure-numpy (fast).
HONEST grokking finding: NOT classic grokking — held-out acc rises EARLY with training (0.90 by
ep150 as train hits 0.99), peaks 0.919 ~ep500, then plateaus; no late jump (expected: 5k-row tabular
data w/ informative features, not a tiny algorithmic set). But the grokking INGREDIENTS (weight decay
+ long train + best-held-out checkpoint) still beat trees. LARGER models did NOT help: (128,64)=0.9745,
(128,64,32)=0.9746, (64,32)wd0.1=0.9779. Curve saved data/models/grokking_curve.json; compare in
model_comparison.json/neural_sweep.json. 25 tests pass.

TODO (efficiency/robustness): process-tree kill on subprocess timeout (the lucene 7.75hr escape) +
graph-metric guards on huge graphs, then cleanly re-mine guava/lucene real architectural labels.

## Architectural-only + larger training (2026-07-22, later)

- "20-hour background process" was the healthy IDLE Streamlit dashboard (PID varies; ~6min CPU/19hr,
  health ok) — NOT a stuck test. `node mcp/server.mjs` (36hr, idle) is IDE tooling. Nothing hung.
- STRICT architectural-only filter: `dsarp/mining/refactoring_miner.py` ARCHITECTURAL_REFACTORINGS +
  `is_architectural()`. Keeps Move/Extract Class/Interface, Move/PullUp/PushDown Method, Move Attribute,
  package moves. DROPS code-level (Extract Method, Rename Method/Var, Change Access/Modifier, ...).
  `scripts/mine_and_align_refactorings.py` uses it + added `--skip-mine` (reuse cached RM json).
- LARGER training attempt hit the real bottleneck: `git fetch --depth=500` on BIG repos is very slow
  (tika deepen+RM ~83min; log4j2/struts/maven/guava never deepened, job ended after tika). RM itself is
  fast; git-history download is the cost. Added `java -Xmx6g` + 900s RM timeout + 600s fetch timeout.
- Recovered via cached RM data -> trained on 5 real repos (commons-cli/lang/io/collections + TIKA,
  557 architectural refactorings) = 1163 rows/468 pos. **LORO=0.9248** (best/most-realistic yet).
  Deployed ranker = 5 repos/1163, Cassandra excluded. Feature importance now catalogue_rank>centrality>
  coupling (not just graph_delta). 25 tests pass.
- TODO to go bigger: remaining big repos (log4j2/struts/maven/guava/spring/lucene) need history; FRESH
  `git clone --depth N` is faster than deepening a depth-1 clone. Offer as a bounded background job.

## RefactoringMiner real historical labels — DONE (2026-07-22)

Decisions (user): Cassandra stays STRICTLY UNSEEN (no training on it); RefactoringMiner on
bounded mid-size repos. Downloaded official RefactoringMiner 3.1.4 -> `tools/RefactoringMiner-3.1.4/`
(150MB). Windows launcher classpath too long for cmd -> invoke `java -cp "lib/*"
org.refactoringminer.RefactoringMiner` from the RM dir (relative cp) with Windows-style paths.
`scripts/mine_and_align_refactorings.py`: deepen clone (git fetch --depth N) -> run RM (-a branch)
-> parse events -> keep ARCHITECTURAL types -> align with structural smells (SmellRefactoringAligner)
-> real labels + weak fallback -> dataset -> retrain. Ran on commons-cli/lang/io/collections @depth500:
1075/388/601/2184 refactorings mined, 44/97/126/21 architectural, TOTAL 667 rows/293 pos/4 repos.
**LORO=0.9709** — first non-degenerate score (real labels add variance). Deployed ranker = 4 repos/667.
Also NEW this turn: `dsarp/smells/detector.py` (Cyclic/Hub-Like/Unstable/God Component — all smells,
not just cyclic) wired into prepare_evidence; **accuracy gate** in pipeline (`quality_gate`:
min_confidence/require_valid/require_evidence + `--min-confidence`) — only valid high-accuracy
suggestions emitted (commons-io dropped 12/78, 100% emitted hallucination-free). 25 tests pass.

Researched (user asked): **Block goose** (MCP tools + autonomous agent LOOP + subagents,
provider-agnostic) and **Microsoft SkillOpt** (skill .md files as trainable params, validation-gated
edits + rejected-edit feedback). Mapping: add runtime AgentLoop + MCP-server exposure (goose-like)
and skill-file optimization from validator/HGRS feedback (SkillOpt-like). NOT yet implemented.

Honest caveats: SmellRefactoringAligner is permissive within a repo (shared package prefix inflates
neighbourhood matches -> many positives); recent commits skew to code-level refactorings (Change
Access Modifier etc.), architectural ones need deeper history; deployed model is the 4 RM mid repos
(giants deferred per user). Next: tighten aligner precision; build the goose-like AgentLoop + SkillOpt.

## FULL-SCALE real training — DONE (2026-07-22)

Ran `scripts/build_real_repo_dataset.py --config train --train` on the real machine.
Cloned (shallow) + indexed **12 real repos** (~20k Java files): tika(1458f), log4j2(1495f),
struts(1481f), lucene(4119f), commons-lang(263f), commons-collections(367f), maven(1597f),
guava(1997f), spring-framework(5319f) + commons-cli/io/text. Cassandra excluded by guard.
Result: **2244 real rows / 744 positives**, sklearn.GradientBoosting, **LORO mean=0.9936**
(no longer degenerate 1.0 — spring=0.9333, tika=0.99, rest 1.0). Real learned ranker is ACTIVE in
inference and discriminates (Extract Interface/Dependency Inversion learned=1.0, Introduce Facade=0.0).
Feature importance dominated by graph_delta (expected: weak labels are graph-derived).
Fixed a real bug: LORO folds were overwriting the deployed ranker.pkl — added `persist=False`
to fold training so the production model stays full-data (12 repos/2244). Disk: 686GB free, used ~min.
Dataset: `data/training/real_multi_repo_train_candidates.jsonl`; stats + generalisation report refreshed.

## Real-repo training (tool-free, weak supervision) — DONE

`dsarp/alignment/weak.py` (GraphWeakAligner) + `scripts/build_real_repo_dataset.py`.
Clones real repos shallowly → source index → import graph → REAL graph smells (cycles/hubs)
→ deterministic candidates → WEAK labels (only strongest fixer per smell = positive, rest =
negative, so both classes exist; capped at 0.6 vs historical labels). No JVM tools needed;
Cassandra blocked. Verified: 4 real Apache repos (commons-cli/io/text/csv) → 156 rows,
52 pos / 104 neg, sklearn.GradientBoosting engaged, structural features only (no names).
commons-cli's REAL cycle (org.apache.commons.cli ↔ .help) drives its positives.
Caveat: LORO=1.0 here is degenerate-clean because the weak label is a deterministic graph rule
that transfers perfectly; real RefactoringMiner *history* labels are needed for a meaningful LORO.
25 tests pass (added weak-aligner both-classes + no-fabrication tests).

Note: "graphify" is NOT a package/module here (not installed, not in code). Our own graph
build/slice/cycle-detection works (proven on real commons-cli: 11 nodes, 1 real cycle).

## Next tasks

- RefactoringMiner (JVM) for real *historical* labels → non-degenerate LORO. Execute-mode wired.
- Scale real-repo dataset to the 9 training repos (large clones — needs user approval for size).
- Optional LoRA once masked chat dataset > 200 examples.
- Add auth to FastAPI before any non-local exposure.

## Problems / risks

- Token policy: never load large JSONL/logs/graphs/models into context — use summaries + evidence IDs.
- `.gitignore` keeps raw/generated data out of git; `data/samples/` + `data/memory/` tracked.
- `configs/local.yaml` provider is `ollama` (qwen2.5-coder:3b) — tests force offline to stay hermetic.

## 2026-08-05 — four measurement defects found by auditing BEFORE-builds

Auditing every repository's *before*-build (the state prior to any refactoring) found
failures that had been attributed to our refactorings. A before-build failure cannot have
been caused by a change not yet applied, so each of these invalidated its own measurement.

1. **`_copy_repo` destroyed source packages named `build`** — `ignore_patterns("build")`
   matches at any depth, and `org.apache.commons.io.build` is a real commons-io package.
   Every working copy lost it and failed with 88 "package does not exist" errors.
   *All commons-io results predating this are invalid.* Fixed: `target`/`build` are skipped
   only beside a build file. Tests: `tests/test_copy_preserves_source_packages.py`.

2. **Karaf requires `package`, not `compile`** — two independent causes:
   maven-dependency-plugin:copy needs siblings as jars (MDEP-187), and the reactor builds
   `karaf-maven-plugin` then uses it, needing the descriptor only `package` generates.
   Fixed: `compile_repo` escalates to `package -DskipTests` on those signatures only.

3. **`verified` did not imply the build compiled** — `both_ok` asked only whether both
   detectors measured. Designite parses source, so it measures a broken tree happily.
   21 historical reports say `verification_status: verified` with
   `build_after_refactoring: compile_failed`. Fixed. The learned ledger was never affected:
   `build_ledger` filters on the build status directly.

4. **The budget investigation was chasing a non-variable** — Karaf "broke the build" at
   budgets 16, 32 and 151 and did nothing at 2. Its before-build carried the identical
   error every time, so no budget could ever have produced an accepted pass.

### Open, highest value next

**Plans are validated individually but applied together.** `_types_touched` only detects two
plans touching the same type, and `SourceFacts` has no inheritance knowledge whatsoever. Two
individually-safe moves can separate a subclass from its superclass, making a package-private
member inaccessible. This is the signature of commons-validator pass 3's before-build failure
(`LuhnCheckDigit` in `validator.digit` extending `ModulusCheckDigit` in `validator`, both
originally in `routines.checkdigit`). An inheritance-aware conflict filter is the next fix.

### Demo status
`apache-commons-validator` pass 1 (Arcan 20->13, Designite 91->86) had a clean before-build
and is unaffected by all of the above.
