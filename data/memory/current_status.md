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

### Result: commons-io 328 -> 298 (9.1%), verified, six smell types

The inheritance guard closed the loop on the repository whose numbers were void this
morning. Causally attributed, not merely correlated: the guard deferred four plans, one of
them verbatim the plan that broke the previous run -

    would move org.apache.commons.io.file.CountingPathVisitor away from its superclass
    org.apache.commons.io.file.SimplePathVisitor

Pass 1 compiled and was kept (Arcan 148->130, Designite 403->390, both tools measured both
sides). Pass 2 broke the build and was rolled back. Smell types reduced: Cyclic Dependency
-16, Unstable Dependency -8, God Component -3, Cyclically-dependent Modularization -2,
Deficient Encapsulation -1, Dense Structure -1.

This is now the strongest demo case: six smell types, both detectors, and a verdict the
gate refused to inflate on the pass that failed.

## 2026-08-31 — Spoon agent: a SECOND transformer, wired to the log4j predictions

A local-model agent that turns the transformer's advisory predictions into executable moves,
applies them with Spoon, and cross-checks with Arcan. Runs beside OpenRewrite, not instead
of it: OpenRewrite dies on the target repo's Maven build, Spoon parses with `noClasspath` and
does not care whether the repo resolves — which is the point on repos of log4j2's size.

NEW MODULES
  dsarp/models/providers.py        OpenAI-compatible local client (Ollama/vLLM/llama.cpp).
                                   NOTE: `dsarp.models` was imported by pipeline.py:19,
                                   multiagent.py:193 and agents/explainer.py and DID NOT
                                   EXIST — the explanation pipeline and --ai-recipes were
                                   both dead. 4 tests were failing on it; now 99 pass.
  dsarp/refactoring/spoon_plan.py  op allowlist + validation against SourceFacts
  dsarp/tools/spoon_runner.py      build/invoke the driver jar
  dsarp/agents/spoon_refactor.py   propose -> apply -> re-detect -> verdict
  tools/dsarp-spoon/               Spoon 10.4.2 driver (shaded jar, builds clean)
  .claude/skills/spoon-refactoring/SKILL.md   the specialist instructions, loaded verbatim
                                   as the model's system prompt so documented rules and
                                   enforced rules cannot drift

  CLI: dsarp multiagent --repo <r> --spoon --model <tag> [--base-url] [--spoon-budget N]

ONE OP: `moveClass`. Everything else the model may propose is rejected by the allowlist.
Extract Method is the transformer's most confident prediction on log4j2 and is NOT
executable — the agent declines it rather than faking it.

SPOON FINDINGS (cost three failed attempts each, do not re-derive):
  1. Reparenting a CtType does NOT move the CtTypeReferences naming it. Each holds its own
     package reference. Without an explicit retarget pass the file lands in the right
     directory with the right package declaration and the old package's callers no longer
     resolve it. Looks perfect, does not compile. javac is in the test for this reason.
  2. The type must be removed from its old CompilationUnit's declaredTypes BEFORE
     `delete()`, or the printer later walks a null and NPEs.
  3. The SNIPER printer cannot be used for moves. It preserves formatting by slicing the
     original source text, and a detached type no longer has any -> StringIndexOutOfBounds.
     Using the default printer instead, which REFORMATS every file in the modeled source
     root. Acceptable only because the target is a throwaway copy measured by Arcan. A
     reviewable patch would need sniper or a per-CU printer.
  4. Shading Spoon copies a signed jar's META-INF signatures and the JVM then rejects the
     uber-jar ("Invalid signature file digest"). The pom filters *.SF/*.DSA/*.RSA.

VERIFIED: driver moves a class across packages, rewrites the caller's import, and the result
compiles under javac (tests/test_spoon_driver.py). 716 log4j2 predictions load, SourceFacts
scans the repo in 3.2s, prompts are grounded in real crossing types.
NOT YET RUN: the full --spoon pass on log4j2 (needs a Nemotron tag pulled; Ollama here has
only qwen2.5-coder). No measured smell delta from this agent yet.

Verification is BATCHED — one baseline, all edits, one re-measure — because Arcan on log4j2
costs minutes per run. Per-edit attribution would be better evidence.

################################################################################
PER-CANDIDATE ATTRIBUTION (supersedes the batched note above)
################################################################################

The "per-edit attribution would be better evidence" note was acted on. It changed the
conclusion, so the batched numbers above should not be quoted on their own.

BATCHED, pdfbox, 7 moves applied together:   952 -> 957, targeted +5, verdict
  rejected_smells_increased. Reads as "the agent makes things worse".
INDIVIDUALLY, the same candidates, one per trial (scratchpad/outcome_labels.py):
  8/8 compiled, 4/8 reduced the targeted smell. The +5 was ArrayEntry (+1 targeted,
  +2 collateral) plus three no-ops swamping four genuinely good moves.
  -> data/outputs/outcomes/apache-pdfbox/outcomes.json

So the ceiling on batching is not candidate quality, it is interaction between moves applied
to one tree. Isolated application is the configuration with a measured positive rate.

BACKEND COMPARISON, identical moves through both (scratchpad/backend_compare.py):
  Spoon        5/5 compiled, 2/5 reduced targeted
  OpenRewrite  2/5 compiled, 0/5 reduced targeted
  Where both compiled they agreed exactly on the smell delta. OpenRewrite's deficit is
  execution (ChangeType left the tree unbuildable on 3/5), not judgement.
  -> data/outputs/backend_compare/apache-pdfbox/backend_compare.json

WHICH FEATURES ACTUALLY PREDICT OUTCOME (dsarp/dataset/ranker.py):
  The 9 MOVE_FEATURES have IDENTICAL means across reduced/not-reduced on the 8 labelled
  candidates (name_affinity 0.000/0.000, pkg_distance 1.250/1.250, depth_from 5.000/5.000).
  Leave-one-out 0/8 against a 0.500 majority baseline. They describe the move; outcome
  depends on the structure the move acts on.
  The 9 GRAPH_FEATURES separate 4 of 9, the strongest being fan_out_from 10.75 (reduced)
  vs 20.75 (not) - a 2x gap. would_close_cycle is constant 1.00 on all eight, so it is
  untested here, not useless.
  n=8 is too small to TRAIN on and no trained accuracy is claimed from it.

HONEST RANKER NUMBERS (mined data, repo-held-out folds):
  Gold candidate originally sat at position 0 in every group, so "always pick the first"
  scored P@1 = 1.000. After shuffling, ranker P@1 fell 0.65 -> 0.55. Quote 0.55.

################################################################################
TWO MEASUREMENT BUGS FOUND WHILE RUNNING THE FULL EXPERIMENT (2026-09-12)
################################################################################

Both produced numbers that looked like results. Any test count or smell delta recorded
before this section should be re-derived rather than quoted.

1. SPOON INVENTS IMPORTS -> whole runs lost to a quality gate.
   Spoon's printer emits an import for a type that exists only as a lambda's INFERRED
   functional interface. `compoundWords.forEach(word -> ...)` printed
   `import java.util.function.Consumer;` into CompoundCharacterTokenizer, which never names
   Consumer. pdfbox fails the build on UnusedImports, Arcan then measured a tree that had
   not compiled, and the run reported 952 -> 2 smells, targeted -946. A 99.8% improvement,
   entirely fake. verdict() caught it as inconclusive_quality_gate_failed.
   FIX: dsarp/refactoring/java_text.py, shared by the Spoon and OpenRewrite arms. Scoped to
   the files the backend actually changed -- an unused import IS a dependency edge Arcan
   counts, so pruning tree-wide would lower the smell count by itself and credit the
   refactoring for it.
   With the fix the identical 4 moves gave 952 -> 951, targeted -1, collateral 0.

2. TEST TOTALS READ OFF THE LAST REACTOR MODULE.
   Maven prints one surefire summary PER MODULE and no aggregate. run_tests() kept the last
   match, with a comment asserting it was the reactor summary. It is not.
     pdfbox   reported   38 run / 0 fail   ACTUAL 2050 run / 0 fail / 0 err
     log4j2   reported  940 run / 6 fail   ACTUAL  950 run / 6 fail / 29 ERRORS
   So pdfbox's positive result is much STRONGER than recorded (2050 passing, not 38) and
   log4j2's damage much WORSE (35 broken tests, not 6).
   This also explains the tika oddity logged earlier as "status failed, 0 failures, 0
   errors, 726 run, inconsistent, untraced": the failing module simply was not the last one.
   FIX: sum module summaries, skip lines carrying "Time elapsed" (those are single test
   classes inside a module already counted). tests/test_test_counts.py.

GRAPH SELECTION DID NOT GENERALISE.
  fan_out_from separated reduced from not-reduced on 8 pdfbox candidates (10.75 vs 20.75).
  Used to pick 4 of N legal moves on unseen repos it predicted nothing:
    tika   picks at 16-24 -> 314 -> 326 (+12), 1 test broken
    log4j2 picks at 7-16  -> 677 -> 684 (+7), 35 tests broken
  One feature, one repo, n=8. Do not retune it on three batch-level points.

STANDING: batched full-repo passes 1 of 4 (pdfbox -1 only). Isolated per-candidate 4 of 8.
Isolated remains the only configuration that reliably reduces a targeted smell.

MOVECLASS IS NOT SEMANTICS-PRESERVING WHERE DISPATCH ORDER FOLLOWS CLASS NAME.
  tika: ServiceLoaderUtilsTest.testSort failed after moving FileCommandDetector from
  tika.detect to tika.utils. ServiceLoaderUtils.sortLoadedClasses sorts by
  CompareUtils::compareClassName, so the relocated detector sorts LAST instead of third and
  service dispatch order changes. fix_references correctly rewrote the test's reference to
  the new FQN; nothing can know the hardcoded EXPECTED ORDER also had to change.
  Invisible to the compiler and invisible to the smell count. Only the project's own tests
  catch it -- which is the argument for keeping the test stage in the gate.
  Generalises to any repo using ServiceLoader, SPI files, annotation scanning, or
  name-ordered registries. A move that is legal, type-correct and smell-reducing can still
  be wrong.

TIKA'S TEST RUN IS PARTIAL. The reactor halts at the first failing module (tika-core), so
every module after it is SKIPPED. "1 failure in 734" means 1 failure before the run aborted,
not a clean full suite. Do not read it as full behavioural coverage.

  MODULE COVERAGE OF THE TEST STAGE (measured, 2026-09-12):
    pdfbox   13 passed   0 failed    0 skipped  -> complete suite, 2050 tests, trustworthy
    tika      3 passed   1 failed  119 skipped  -> 4 of 123 modules ran
    log4j2    6 passed   1 failed   34 skipped  -> 7 of 41 modules ran
  The reactor halts at the first failing module, so tika's "1 failure" and log4j2's "35
  broken" are LOWER BOUNDS taken before the run aborted. The true damage can only be larger.
  Consequence: the one positive result (pdfbox -1) is also the only one with full test
  coverage behind it, and the two negatives are worse than their numbers look, not better.
  To get a real figure, the test stage needs -fae (fail at end) so later modules still run.

################################################################################
BACKENDS ARE EQUIVALENT (settled 2026-09-12, do not re-litigate)
################################################################################
Identical 5 moves, one shared pdfbox baseline, measured both ways:
                       compiled   reduced targeted
  Spoon                  5/5          2/5
  OpenRewrite BEFORE     2/5          0/5
  OpenRewrite AFTER      5/5          2/5
Per-candidate agreement after the fix is EXACT on all five (+1/+1, 0/0, -1/-1, 0/0, -1/-1).

The 2/5 was never a capability gap. Two defects in OUR pipeline, nothing to do with the tool:
  a) ChangeType rewrites references TO a moved type and leaves references FROM it alone, so
     the moved file lost the imports for ex-siblings it still names. Spoon escapes this only
     because it reprints the moved file with real imports.
     -> java_text.add_origin_imports, moves read back from rewrite.yml via recipe_moves().
  b) the tidy pass was a NO-OP. OpenRewrite prints changed-file paths relative to the maven
     PROCESS cwd; we joined them onto repo_path, got paths that do not exist, skipped every
     file, and pdfbox kept failing the four RedundantImport errors the pass existed to remove.
     -> _java_files resolves against cwd too, and refuses anything outside the repo copy.
Both were found only because KEEP_LOGS=1 kept the work dirs. "It did not compile" is not a
finding; the javac line is.

TEST SOURCES ARE NOW IN THE PRECHECK MODEL.
  A move can be legal for main and illegal for tests. commons-validator: ISBNValidator moved
  routines -> routines.checkdigit, main compiled, Arcan measured 21 smells, then testCompile
  died on "ISBN10_REGEX is not public". precheckInRoot only ever modelled src/main/java.
  illegalReason already scanned the whole model and its userPkg.equals(from) test would have
  caught it -- the test file was simply never parsed.
  FIX: newLauncher(root, cp, compliance, includeTests) adds <module>/src/test/java, derived
  from the layout so a caller cannot forget it. Falls back to main-only if the model build
  throws (test-scope types unresolvable) and reports testsModelled=false so a weaker verdict
  never passes as a full one. module_classpath switched to includeScope=test + test-classes.
  VERIFIED: ISBNValidator now ILLEGAL with
    "ISBNValidatorTest in ...routines uses field ISBNValidator.ISBN10_REGEX, not public"
  CodeValidator stays legal. commons-validator 2 legal -> 1 legal.

################################################################################
THE 50% FIGURE DOES NOT SURVIVE BETTER MEASUREMENT (2026-09-12)
################################################################################
Old: "4/8 = 50% of moves reduce the targeted smell". That number was produced by
  - HEAD sampling (all candidates came from the few worst findings),
  - targeted-delta only (ignores what the move does to every other smell),
  - no test verification,
  - 4 of 9 features constant zero because features_for() was called without signatures.

Re-measured on pdfbox, stride-sampled across the ATDI range, n=15 so far:
    label        targeted smell fell             3/15 = 20%
    label_strict targeted fell + tests pass      3/15 = 20%
    total smells fell (any cause)                4/15 = 27%
    label_net    targeted + tests + total fell   2/15 = 13%
Quote label_net. It is the only one that means "the codebase got better and still works".

TARGETED-ONLY IS WRONG IN BOTH DIRECTIONS, not merely lenient:
  PDResources                   targeted -2, collateral +3 -> label=1 but the repo got WORSE
  PDAppearanceStream            targeted  0, collateral -4 -> label=0 but the repo got BETTER
  PDTransparencyGroupAttributes targeted  0, collateral -11 -> label=0 but the repo got BETTER
  The "reduced" set and the "improved" set are different sets, not subset and superset.

VALUE IS WILDLY NON-UNIFORM, and this matters more than the rate:
  MissingOperandException, contentstream.operator -> contentstream, Cyclic Dependency:
  952 -> 712 total (net -240, a QUARTER of the repository's smells), 2050 tests pass,
  all 13 modules. One class move. Arcan counts Cyclic Dependency per participating element,
  so breaking one large package cycle clears every finding it generated.
  A dozen other moves did nothing at all. Chasing a uniform 50% hit rate is probably the
  wrong goal; reliably FINDING the rare cycle-breaking move is worth far more.

Build-failure guard confirmed working: PDMarkedContent and PDAnnotation both came back
total_after=57 (the same shape as the fake -946) and both scored label=0 via
quality_gate_failed. They are excluded, not celebrated.

################################################################################
THE METRIC WAS THE PROBLEM (2026-09-13) -- read this before trusting any rate above
################################################################################
Bytecode cycle detection (tools/dsarp-archunit, ArchUnit importer + Tarjan) on the same
baselines Arcan measured:

    repo       packages  CYCLES  sizes              Arcan "Cyclic Dependency"
    pdfbox        103       5     51, 7, 4, 3, 2            802
    log4j2        158       5     50, 15, 2, 2, 2           535
    tika          271      11     18, 8, 8, 7, 3...         245

pdfbox does not have 802 cyclic-dependency problems. It has FIVE cycles, one containing 51
of its 103 packages. Arcan counts per-element participation in a handful of giant strongly
connected components, not distinct defects.

CAN ANYTHING DISSOLVE THEM? No. Greedy feedback arc set (cheapest edge on a cycle, repeatedly):
    pdfbox  51 pkgs, 349 internal edges, density 0.137 -> cut 167 edges, abstract 1177 classes
    log4j2  50 pkgs, 385 internal edges, density 0.157 -> cut 156 edges, abstract 1164 classes
    tika    18 pkgs,  91 internal edges, density 0.297 -> cut  43 edges, abstract  255 classes
Our best single invertEdge abstracted 4 classes. pdfbox would need ~800 successful inversions
at the measured 36% rate and would gain 1177 new interfaces. The cure is worse than the disease.
These components are uniformly interwoven -- ~14% of all possible directed edges exist and half
must go -- so there is no cheap cut to find.

WHAT THIS EXPLAINS RETROACTIVELY:
  - MissingOperandException's -240 smells detached elements from the 51-package SCC; the cycle
    survived. It was never "breaking a cycle".
  - All three ranking failures (severity -0.127, leaf-first -0.115, learned regressor 0.689 but
    -0.786 on tika) follow directly: the target was "how much did you peel off the blob", which
    is dominated by whichever move detaches a big subtree. That metric GENERATES outliers.
    No ranker could have generalised over it.
  - invertEdge beating moveClass 36% vs 19% is still true and still the better operation. Both
    were shaving a component neither could dissolve.

WHERE THE VALUE ACTUALLY IS: cheap edges. pdfbox has 57 feedback-arc edges carried by <= 2
classes, several by exactly one (contentstream -> blend, markedcontent -> text, state ->
pdmodel, filter -> util). Each is one invertEdge from gone. They do not dissolve the SCC, but
"this specific edge no longer exists" is verifiable by the ArchUnit oracle, reviewable by a
human, and is what ArchUnit users already enforce. Stop claiming smell removal; claim edge
elimination with a stated cost.

CHEAP-EDGE ELIMINATION IS DEAD (2026-09-13). Ruled out by measurement, not opinion.
  Aimed the pipeline at the 57 pdfbox feedback-arc edges carried by <= 2 classes, on the
  reasoning that each was one invertEdge from gone. Precheck: 0 LEGAL OF 18.
    not a class         7   PDImage, COSObjectable -- already interfaces
    no instance method  4   Version, MissingImageReaderException -- utility / exception
    constructs          4   PDLineDashPattern -- value objects, built directly
    reads field         2   BlendMode.NORMAL -- enum constant
    static              1   Hex.writeHexByte()
  An edge carried by ONE class is carried by one class because that class is a utility,
  constant, exception, value object or already an interface: single-purpose types used one
  narrow way. That is what makes the edge cheap to IDENTIFY and simultaneously what makes it
  impossible to invert. Cost-to-identify does not predict cost-to-fix; the two sets are close
  to disjoint. Seven of the eighteen were already interfaces -- pdfbox's architects applied
  DIP there long ago and the cycle persists regardless.

THREE TARGETS NOW RULED OUT BY MEASUREMENT:
  1. dissolve the SCC        167 edges / 1177 classes on pdfbox -- unreachable
  2. reduce smell counts     counts participation in 5 components; generates outliers;
                             three rankings failed on it (-0.127, -0.115, 0.689 but -0.786)
  3. eliminate cheap edges   cheap ones are structurally un-invertible (above)
WHAT SURVIVES: invertEdge on behaviour-rich classes, 8/22 net across three repos, beating
moveClass on every one. Those are MID-COST edges. Rank by invertibility, not by class count.

LOOSENING LEGALITY DID NOT HELP OUTCOMES (2026-09-13). Type constraints replaced the checklist:
  legality on the same 12 pdfbox candidates 1 -> 4, compile rate 50% -> 61%. But three-repo
  invertEdge, same script and baselines:
      checklist    n=22 compiled=11 net=5 (36%)
      constraints  n=23 compiled=14 net=2  (9%)
  More legal candidates pushed the top-8 cut down the ranking into marginal ones (tika 3/6 -> 0/7).
  Outcomes were never bottlenecked on legality; they are bottlenecked on SELECTION. Constraints kept
  on: they are more correct, and selection is the separate problem.

SELECTION, FIFTH ATTEMPT, FIRST TO GENERALISE (dsarp/dataset/selection.py).
  Screen features by direction consistency across repos BEFORE fitting, target binary label_net
  (not smell delta). 9 of 22 features agree in every repo with both classes. Held out by repo:
      precision@k  model 0.21   shipped ATDI 0.11   random 0.18
  Beats both. Small: 14 wins / 80 candidates; tika 0/2 (ATDI 1). Claim the METHOD, not the number.
  Correction: the first heuristic selected LOW fan_out_from off 8 pdfbox rows. Across 103 rows it is
  consistently POSITIVE -- that heuristic selected against its own signal.

SELECTION CONFIRMATION FAILED (2026-09-14). Read before quoting any selection result above.
  Pre-registered: fresh candidates only, 8 a-priori features, k=3 per arm on pdfbox/log4j2/tika,
  rule "model > shipped AND model >= random", selection frozen in preregistration.json before the
  first candidate was applied.
  First run was corrupted by two MEASUREMENT bugs, both since fixed (e519c67):
    - working copies omit target/, so module_classpath on a copy lost the module's own compiled
      classes: precheck on the original (58 entries) said legal, apply on the copy (56) refused.
      6 of 9 tika picks never applied. Every labelling script had this shape.
    - fix_references added an import for a name mentioned only in a comment; checkstyle failed.
  Re-measured only the 7 invalidated candidates, selection unchanged:
      model 1/9   shipped 0/9   random 2/9   ->  NOT CONFIRMED
  The held-out 0.21 was noise. FIVE selection attempts, none survives fresh data.
  The one consistent signal in every run: the shipped ATDI order is worst or tied worst.
  Net-win base rate on fresh legal candidates: 3/27, about 11%.

################################################################################
THE VALIDATOR NOW ANSWERS PER EDGE, AND TWO TOOLS AGREE ON THE ANSWER (2026-09-23)
################################################################################
What changed, all in tools/dsarp-archunit + dsarp/tools/{archunit_runner,jdeps_runner}.py:
  * each package edge carries the CLASS PAIRS that create it, the pairs where the consumer
    CONSTRUCTS the target, and the dependency KINDS ("Method calls method", "Field has type").
  * edge_verdict(before, after, from, to): is that edge gone, what did it cost in new edges,
    were new cycles introduced, and what still carries it.
  * jdeps (-verbose:package) re-reads the same class files and cross-checks the edge set.
    commons-validator: 7 edges, 7 agreed. ArchUnit has silently imported zero classes before;
    a blind oracle makes "the edge is gone" vacuously true.
  * compile_repo(goal="test-compile") for verdicts: `mvn compile` skips test compilation, so a
    move that stranded the test sources still reported `compiled`.

CANDIDATE GENERATION NOW ASKS THE COMPILER, NOT A REGEX. The text scan named 2 types for a
commons-validator edge the bytecode says is carried by 6 dependencies; inverting both left the
edge standing.

TWO MECHANICAL BLOCKERS ON DEPENDENCY INVERSION, both readable from the snapshot:
  1. the consumer CONSTRUCTS the target -- retargeting the declaration leaves `new Impl(...)`,
     and that reference holds the edge up alone. commons-validator checkdigit -> routines:
     6 dependencies -> 2, edge survives, the 2 being `new CodeValidator(...)`.
  2. the consumer DECLARES NOTHING of that type -- pdfbox operator.color depends on
     PDGraphicsState 16 times, all "Method calls method". Spoon refuses it after 70s of model
     building; the snapshot says so for free.

REACH, every in-cycle edge on pdfbox (380 edges, was sampling 5):
    inversion not blocked      70 (18%)
    no declaration to retarget 111 (29%)
    some target constructed   256 (67%)
    carried by one class      175 (46%)
    nothing we have applies   142 (37%)
The pipeline has been aiming its main operation at 18% of the problem.

MOVES ARE NOW ARITHMETIC, NOT A RANKING (dsarp/tools/jdeps_runner.move_effect).
jdeps -verbose gives the class-level graph INCLUDING same-package edges -- which ArchUnit
drops and which decide what a move costs, because a class leaving its package turns every tie
to its old neighbours into a package edge. Relabel one class, re-derive the package graph,
diff. pdfbox: of 342 single-carrier in-cycle moves, 109 remove the targeted edge and 77 leave
the graph strictly smaller (best: Loader -> pdmodel, -18 edges +2).
Checked against a measured case: moving PDGraphicsState into operator.color was predicted to
leave the edge and add 12; measured, it left the edge and added 11. Seconds, not 208.

PLANNED MOVES, MEASURED (2026-09-23). Six per repo, chosen by predicted net edges, applied with
Spoon, built with test sources, judged by the bytecode oracle and cross-read by jdeps, tests run
against the baseline:
    apache-pdfbox   moveClass  6/6 applied  6/6 built  6/6 edge removed  6/6 tests pass
                    invertEdge 6 candidates, 2 applied, 0 built, 0 edges removed
    predicted new edges vs measured: 2/2, 15/15, 1/1, 10/10, 0/0, 2/2 -- exact on all six
    log4j2 so far:  StatusConfiguration -> core.util (removes 9, adds 0), ScriptArbiter ->
                    core.config (removes 6, adds 0), Required -> core.config (removes 13,
                    adds 4 where 3 were predicted); all tests pass.
Inversion failed six distinct ways: no instance method on the movable declaration; the consumer
declares nothing of that type; the target is already an interface; the target is an annotation;
and twice it applied and broke compilation. Four of the six are visible in the snapshot before
any Spoon run.

CAVEAT THE GRAPH CANNOT SEE: moving a public type renames it for every downstream user. Loader
and COSObjectable are public pdfbox API, so those two are major-version changes however clean
the edge arithmetic is. Reported per candidate, not silently counted as a win.

################################################################################
THREE-REPO RESULT: PLANNED MOVES WORK, INVERSION ALMOST NEVER DOES (2026-09-23)
################################################################################
Six planned moves per repo, each paired with an inversion aimed at the SAME edge. Applied with
Spoon, built with test sources, judged by the ArchUnit edge oracle, cross-read by jdeps, tests
compared against the repository's own baseline:

    repo        op          n  built  edge removed  clean  ACCEPTED
    pdfbox      moveClass   6    6         6          6       5
                invertEdge  6    0         0          0       0
    log4j2      moveClass   6    6         6          6       6
                invertEdge  6    0         0          0       0
    tika        moveClass   6    6         6          6       3
                invertEdge  6    1         1          1       1
    TOTAL       moveClass  18   18        18         18      14
                invertEdge 18    1         1          1       1

PLANNER ACCURACY (predicted before applying, measured after):
    edges ADDED    exact 14/18, within 2: 18/18
    edges REMOVED  exact  7/12, within 2: 12/12   (only recorded from the log4j2 run onwards)
    jdeps agreed with the oracle on 13 of 13 verdicts it could read.

WHY THE FOUR MOVES WERE REJECTED -- all by tests, none by the structure:
    tika ParseContext x2, tika StringUtils: 24 failures / 17 errors against a baseline of 1/3.
      ParseContext -> metadata was structurally the best candidate this project has produced
      (71 edges removed, 7 added, jdeps agreeing) and it breaks 37 tests. Under the old
      smell-count validator it would have been recorded as a large win. Cause not diagnosed;
      the driver now keeps the test log for rejections.
    pdfbox PDFDebugger: 0 failures on 1994 tests against a baseline of 2050. Fifty-six tests
      stopped running. See tests_no_worse() -- a failure count alone reads that as a pass.

INVERSION'S SIX REFUSAL MODES (17 of 18 never reached a build):
    declares nothing of that type (6) | already an interface (4) | applied then failed to
    compile (4) | no instance method called on the movable declaration (1) | the target is an
    annotation (1) | not a class (1). Four of the six are visible in the snapshot for free.
    The one that worked -- tika ParseContext -> ParseContextApi in metadata -- removed the
    edge, added nothing, and passed, on the SAME edge where the move broke 37 tests. Inversion
    is narrow but safer: it leaves the class where it is, so nothing resolved by name moves.

RULE THIS SUPPORTS: try inversion where the snapshot says it is unblocked, fall back to a
planned move, and let the test run decide. Patches for every accepted change are under
data/outputs/edge_impl/<repo>/patches/.

################################################################################
SPOON AND OPENREWRITE AGREE, WHERE OPENREWRITE CAN RUN (2026-09-24)
################################################################################
The 14 accepted Spoon moves re-applied as OpenRewrite ChangeType recipes, judged by the same
oracle (cycles + jdeps), tests not re-run:
    pdfbox   6/6 agree   same edge removed, same edges added (2,15,1,10,0,2)
    log4j2   5/6 agree
    tika     0/3         the recipe never ran at all
    Where both appliers ran: 11 of 12 identical. The verification is applier-independent.

THE THREE TIKA FAILURES ARE OUR INTEGRATION, NOT THE TOOL. rewrite:run forks a Maven
lifecycle, which executes tika's own maven-dependency-plugin:copy-dependencies, which needs
sibling artifacts packaged. compile_repo already escalates to `package` for exactly this
shape; run_recipe does not. Fix: a package/install -DskipTests pre-step. NOT DONE.

THE ONE REAL DISAGREEMENT: log4j2's @Required (an annotation). ChangeType left
RegexFilter.java importing it and annotating a field `@Required(message = "...")` at the old
FQN, so the build failed. Spoon rewrote it. Whether that is a ChangeType gap on annotation
uses or a file the plugin silently skipped is NOT determined.

NEARLY PUBLISHED A FALSE FINDING ABOUT A THIRD-PARTY TOOL. The first comparison showed
OpenRewrite breaking the build on pdfbox's Loader: it moved the class, rewrote most
references, and left two TEST files importing the old name. That was our pinned plugin
version. Two controlled runs (identical recipe, repo, heap, flags; one variable each):
    -Dmaven.test.skip on/off   no difference, both rewrite test sources
    5.42.1 vs latest           5.42.1 leaves them, 6.46.1 rewrites them
DEFAULT_PLUGIN is now 6.46.1. Every number above is from that version.

WHAT THE RESEARCH ADDED (docs.openrewrite.org, and implemented):
  * residual(repo, fqn) -- after a move NO file should still name the old FQN. Both appliers'
    misses fail this in seconds instead of after a six-minute compile.
  * write_move_recipe() -- ChangeType, then ChangeTypeInStringLiteral, then FindAndReplace
    over poms/XML/properties/META-INF services, then RemoveUnusedImports. Covers the two
    defects NEITHER applier handled: pdfbox debugger-app/pom.xml's <mainClass> and tika's
    tests asserting a moved class's FQN as a string.
  * write_migration_recipe() -- the same move as a recipe for DOWNSTREAM projects, which is
    how the OpenRewrite ecosystem handles a breaking change. Turns "moving Loader breaks
    every dependent" into "and here is the recipe that fixes it".

################################################################################
SWE-REFACTOR CANNOT EVALUATE THIS PROJECT'S PLANNER (2026-10-01)
################################################################################
Zenodo 22001546, extracted (216 zip entries carry ':' in model names like
deepseek-coder-v2:16b, which Windows refuses -- sanitise the names, skip the 81 bundled jars).

WHAT IT CONTAINS: 703 records over 10 Java projects (checkstyle, commons-io, commons-lang,
hibernate-orm, hibernate-search, javaparser, junit4, junit5, mockito, pmd), every one verified
by compiling, running tests and checking purity. Entirely METHOD-level:
    Extract Method 359 | Move Method 146 | Extract And Move Method 133
    Inline Method 35 | Move And Rename Method 16 | Move And Inline Method 14
    Move Class: 0.  Extract Interface: 0.  Package-level: 0.
(The Zenodo record says 1,099; 703 is what the per-project pure_refactoring_data files hold.)

131 of the move records cross a package boundary: checkstyle 50, pmd 32, hibernate-search 22,
commons-io 11, javaparser 9, hibernate-orm 7. All 131 compiled, passed tests, flagged pure.

THE EXPERIMENT (dsarp experiments + git worktrees off the deepened commons-io clone; the shared
clone's working tree was never touched): build the parent and the commit of each benchmark
commit, snapshot package edges with ArchUnit at both, diff.
    commits judged               5 of 5
    targeted edge existed before 5
    targeted edge REMOVED        0
    weights: filefilter->file 10->17, output->root 12->16, input->root 54->54,
             input->root 81->81, root->function 36->36 (that last one moved SEVEN methods)

WHY, AND IT IS STRUCTURAL: developers move methods across edges carrying 36 to 81 dependencies.
This project's planner deliberately targets edges carried by ONE class. The two populations are
close to disjoint, so SWE-Refactor is not ground truth for edge elimination -- not even for
Move Method, and not because the benchmark is weak.

CORRECTION TO THE EARLIER PLAN: "implement Move Method because it is the commonest developer
refactoring" does not follow. It is the commonest, and in this evidence it does not remove
package edges. Move Method would widen reach over a population where the success criterion
does not apply. Decide what Move Method is FOR before building it.

WHERE SWE-REFACTOR IS STILL USEFUL: standalone, as a method-level refactoring benchmark with
compile/test/purity ground truth -- and as prior art for the validator, since its authors
independently arrived at compile + test + purity, which is this project's gate order minus the
structural oracle.

################################################################################
EXPERT MANUAL ARCHITECTURAL REFACTORING DOES NOT MINIMISE EDGE COUNT (2026-10-01)
################################################################################
Zenodo 18754704, Arcelli Fontana / Milanese / Refolli / Trubiani, "Impact of Refactoring
Architectural Smells on Quality, Security, and Performance Metrics" (674 MB). Each of its
projects ships THREE source trees: Init (upstream), noModularity and noDependency (both
manually refactored by the authors to remove architectural smells). That is architecture-level
ground truth with source on both sides -- the thing SWE-Refactor does not contain.

Commons Compress ships precompiled classes for all three, so our own oracle measures them
directly with no build:
    version        packages classes  cycles      participation  package edges
    Init              36      589    [3, 25]          28             108
    noDependency      37      595    [3, 15]          18             109
    noModularity      56      585    [9, 29]          38             162

Init -> noDependency: 10 edges removed, 11 added => NET +1 EDGE. Cycles 2 -> 2, neither
dissolved. But the 25-package cycle became a 15-package cycle, and the 15 is a strict SUBSET of
the 25: ten packages were lifted out of it (archivers, .ar, .arj, .cpio, .dump, .jar, .sevenz,
.tar, .zip, .utils). The experts extracted an `archivers.factory` package and inverted the
dependencies through it.
Init -> noModularity: 13 removed, 67 added, net +54; participation 28 -> 38. Worse by every
measure our oracle has -- splitting packages adds edges by construction.

WHAT THIS MEANS FOR OUR PLANNER, AND IT IS NOT SMALL:
  * move_planner only proposes candidates with predicted_net < 0. The expert dependency
    refactoring is net +1, so OUR PLANNER WOULD NEVER HAVE PROPOSED IT, and the gates would
    not have accepted it.
  * the objective experts pursue is CYCLE PARTICIPATION (28 -> 18, -36%), not edge count. Our
    ranking minimises the wrong quantity.
  * participation is computable from move_effect's after-graph by running Tarjan on it -- no
    build, no new tool. The planner can be re-aimed at the measure experts demonstrably
    optimise.
  * their operation was "extract a NEW package and invert through it". DSARP has no operation
    that creates a package.

A PARTIAL REHABILITATION OF THE SMELL COUNT: participation is what Arcan's per-element counting
approximates, and it tracked the experts' intent here. The earlier finding stands as stated --
participation is a poor PREDICTION TARGET, dominated by outliers, and a fall in it is not
evidence a cycle broke -- but as a DESCRIPTION of what an architectural refactoring achieved it
is better than the edge count this project replaced it with.

Sample: one project measured directly (compress); jeromq building for a second. Do not
generalise from n=1 -- the mechanism (extract a package, invert through it, accept more edges to
shrink a cycle) is what to carry forward, not the exact numbers.

CORRECTION, SECOND PROJECT MEASURED (jeromq, built from the same package's source):
    version        packages classes  cycles   participation  edges
    Init              33      362    [28]          28         159
    noDependency      33      369    [28]          28         156
    Init -> noDependency: 17 edges removed, 14 added, NET -3 | participation 28 -> 28

This contradicts the conclusion written above from compress alone. The two expert refactorings
optimise different scalars:
    compress   net +1 edge, participation -36%
    jeromq     net -3 edges, participation  0%
So "experts optimise cycle participation" is NOT supported at n=2. Retract it.

WHAT SURVIVES BOTH PROJECTS:
  * neither refactoring dissolved a single cycle (2->2, 1->1), which matches every measurement
    this project has made on pdfbox, log4j2 and tika;
  * both RESTRUCTURED rather than monotonically reduced: 10 removed / 11 added, and
    17 removed / 14 added. A planner that only proposes monotone improvements (predicted_net <
    0) would have refused compress's refactoring outright and accepted jeromq's for the wrong
    reason;
  * both ADDED classes (+6, +7) in new packages or new utility types -- an operation DSARP does
    not have at all;
  * no single scalar we can compute -- edge count or participation -- captures both. Neither is
    the objective.

The transferable mechanism, stated in the authors' own words for Jackrabbit: "Create a new
utility class ... in a newly created 'util' package. Move the functionality that is causing
dependencies ... to this new class." Compress's archivers.factory is the same shape. That is a
COMPOSITE: create package, create class, move the dependency-causing members, let references
invert. Method movement is step three of four, which is why moving methods alone removed 0 of 5
package edges in the SWE-Refactor experiment.

################################################################################
THE COMPOSITE EXTRACTION: APPLIES ALWAYS, COMPILES HALF, ACCEPTED NONE (2026-10-01)
################################################################################
dsarp/refactoring/extract_to_package.py implements the operation both expert refactorings in the
Arcelli Fontana package perform: create a package, create a class in it, move the members that
reach across the edge, let the references invert. Run on four repositories through the same gates
as a planned move.

THREE PRECONDITION DEFECTS FOUND BY RUNNING IT, ALL FIXED:
  1. overloaded methods -- _cut_methods takes one declaration per name, so the sibling stayed and
     the call-qualifying pass rewrote it: `public static boolean GenericValidatorSupport.isDate(`.
     commons-validator isDate has 2 overloads, pdfbox Loader.loadPDF has 16.
  2. own-class members used unqualified -- fine in the same package, "cannot find symbol" from a
     new one (log4j2 LogManager). extract_class guards only private/protected, which is correct
     for ITS destination and insufficient for this one.
  3. my own guard refused locals -- `final FastHashMap results = ...` at eight spaces read as a
     field, which took commons-validator from one candidate to none. Fields are matched at
     class-body indentation now.

FINAL RUN, ALL GUARDS ON, 4 CANDIDATES:
    validator ValidatorUtils   compiled, EDGE REMOVED (1 removed, 2 added) -- but a NEW CYCLE
                               appeared: [validator, routines, routines.checkdigit, util.support]
    tika EmbeddedDocumentUtil  compiled, edge NOT removed, 2 removed and 20 ADDED
    log4j2 AsyncLoggerConfig   compile failed (cause not yet diagnosed)
    tika DetectHelper          compile failed (cause not yet diagnosed)
    ACCEPTED: 0 of 4.

WHAT THE TWO COMPILING RESULTS SAY, AND IT IS SPECIFIC:
  * PLACEMENT is a decision we are not making. `<consumer>.support` sits inside the consumer's
    subtree and therefore inherits its position in the cycle, which is how removing one edge
    introduced a four-package cycle. Compress's archivers.factory worked because the root
    depended on the factory and the factory on the leaves -- acyclic by placement.
  * COST is a prediction we are not making. EmbeddedDocumentUtil's two extracted methods dragged
    twenty new package edges with them. The bodies' type references are readable before
    applying, so that candidate could have been refused for free instead of after a compile.

Both are computable before anything is applied, in the same style as move_effect. Until they
are, this operation is implemented and not yet useful: it applies 4/4, compiles 2/4, and is
accepted 0/4.

################################################################################
PACKAGE SPLITTING IS COUNTERPRODUCTIVE: 77 OF 78 PREDICTED WORSE (2026-10-02)
################################################################################
Coverage audit first, from the code rather than the docs. STRATEGIES maps 17 smell types: 8 have
a planner, 7 are declared not automatable, cyclic is handled by the loop. Across 20 repositories
the normalized findings are 2,275 and ALL of them are architecture smells:
    Cyclic Dependency 1120 (49%) | Hub-Like 628 (28%) | God Component 329 (14%)
    Feature Concentration 80 | Scattered Functionality 62 | Unstable Dependency 54
So nominal coverage is ~99.8%. The gap is not coverage, it is VERIFIED EFFECTIVENESS: only
Cyclic has ever been measured against the bytecode oracle.

Hub-Like + God Component + Feature Concentration = 1,037 findings (46%) all dispatch to
plan_god_component, which SPLITS a package: classes sharing a name stem move to a new
sub-package. That is the operation Arcelli Fontana's noModularity trees perform by hand, and
Commons Compress's measured 108 -> 162 package edges and 28 -> 38 participation.

PREDICTED FOR EVERY APPLICABLE SPLIT (no builds; a split is a group move, so move_effect's
relabelling gives the exact result, and that arithmetic was validated at exact-on-14-of-18 and
within-one-on-18-of-18 for added edges):
    78 applicable, 99 refused by the planner's own preconditions
    edges:         77 of 78 INCREASE, median +13, max +34; one tika case -89
    participation: 61 increase, 17 unchanged, ZERO decrease
    verdict:       0 better, 77 worse, 1 neutral
No split is predicted to reduce cycle participation anywhere, in any repository.

METHOD NOTE: the first run took `before` from the ArchUnit snapshot and `after` from the jdeps
graph, which charges any disagreement between the importers to the refactoring. Fixed to one
source; the direction did not change (78 worse -> 77 worse + 1 neutral). By-product: jdeps and
ArchUnit agree on 97% of pdfbox's package edges, 91% of log4j2's, 93% of tika's.

WHAT THIS MEANS. The operation reduces the smell it targets -- a smaller package is no longer a
God Component -- while making the dependency graph worse. Both metrics are real and they
disagree, which is the same conflict the compress noModularity tree shows. Until that is
resolved, "we address God Component" and "we improve the architecture" cannot both be claimed of
this operation, and the 46% of findings it covers are not evidence of improvement.

## Designite smell reduction: the measured ceiling, and a measurement that was void

GOAL. "Most smells Designite reports, refactored." Pursued, measured, and the honest answer is
that the majority is not reachable on the repositories here. The reasons are measurable, so the
target is now a number rather than an aspiration.

### DesigniteJava was running UNLICENSED, and failed silently

`tools/DesigniteJava.jar` logs: "The trial version allows you to analyze an application lesser
than 50000 lines of code in size ... detailed results are disabled." Above the cap it writes every
CSV with its header row and **no rows**, and exits zero. apache-commons-io came back as a clean
zero that way, as did commons-lang, commons-collections and opennlp.

Every Designite number for a repository over 50k lines is therefore void, and the harness would
have reported those zeros as fact. `measure_smells` now refuses such a run (`trial_limit_hit`),
clears stale output first so an old log cannot trip the guard, and passes `-k` when a key is
available via `DESIGNITE_KEY` or `tools/designite.key`. Nothing is registered on this machine --
no entry under `HKCU\Software\JavaSoft\Prefs` -- and there is only one Designite jar on disk.

The unrestricted outputs in `~/Downloads/dsarp repos/Designite` (log4j2 21652 implementation
smells, struts 5630, tika 8175) were produced on a DIFFERENT machine: their File column reads
`/Users/surabhilone/Desktop/Thesis/...`. They are provided third-party evidence, not evidence that
this machine's jar is licensed, and their paths do not resolve here, so the source-dependent
analysis below cannot be run on them.

MEASURABLE SET with the current licence: commons-validator, -cli, -csv, -email, -codec, -text.
Not pdfbox, log4j2, maven, tika, struts, spring, lucene, solr, collections, io, lang, opennlp.

### Two counting errors in the harness, both inflating the target

  * 25 of the 226 "production" findings sat in **test source**. Designite reports test code in the
    Implementation and Design categories, not only in TestabilitySmells. Unutilized Abstraction is
    14 test classes to 3 production ones. The real production figure for commons-validator is 201.
  * Designite reports a method as starting on its **javadoc** line, and javadoc carries `{@code}`
    braces, so balancing braces from there closes the method before its body is read. That made 12
    literals look absent from code they sat in plainly. Fixed with `java_text.code_only` and
    `java_text.body_range`, scanned character by character; tests in
    `tests/test_java_text_code_only.py`.

### What is reachable: 17% of commons-validator, 0.3% validated across six repositories

`dsarp/experiments/addressable.py` sorts every production finding into one of five buckets, each
verdict citing a measured result or a property computed from the source.

commons-validator, 201 production findings: 7 validated, 27 need a name or a design decision,
27 blocked by the published API, 49 the maintainers kept on purpose, 91 no operation. 34 = 17%.

Six measurable repositories, 2085 production findings:
  validated by a measured run        7   0.3%
  mechanical, needs a name/design 1020  48.9%   <- 853 of these are commons-codec
  blocked: published API           119   5.7%
  maintainers kept on purpose       88   4.2%
  no operation in the toolkit      851  40.8%

### Why the biggest target was not a target

Magic Number is 68 of 201, the largest single type. Of those, **49 sit in methods the maintainers
marked `// CHECKSTYLE IGNORE MagicNumber`** -- they considered those literals and decided to keep
them, in writing, in the code. 14 more are 0, 1 or 2, where the digit is plainer than any name.
Seven were genuinely open. A recipe that emitted `CONST_13` would clear the detector's count while
leaving every site it touched worse, so `ReplaceMagicNumberWithConstant` takes the name as a
required option and will not derive one from the value.

Deficient Encapsulation is 20 production findings and **none** are reachable: 64 of the 86 exposed
fields are `public static final` constants, the published API, and exactly one of 23 flagged
classes exposes nothing but mutable state. "Unutilized" public types are used by consumers, not
unused; Designite's own description hedges with "please ignore".

### The stock catalogue is exhausted at 3%

`CommonStaticAnalysis`, all 216 recipe classes in rewrite-static-analysis 2.41.1, on
commons-validator: 6 files changed, compiles, **201 -> 194**, Complex Conditional -6, Long
Statement -1, nothing introduced, 1147 tests green. Three hand-picked recipes got 6 of those 7.
Since the catalogue ran over every finding, a finding of a type it only partly cleared is one it
saw and did not fire on -- the remainder is counted as having no operation, not as reachable.

### Package splitting: 0 of 4, final

log4j2, God Component splits, both metrics: appender compiled but Arcan +1, edges +2, tests FAILED;
selector and manager failed to compile; formatter compiled but edges +4, participation +1, tests
FAILED. None accepted. With the earlier prediction over all findings (0 better, 77 worse) and the
first measured split, package splitting is closed.

## Measured smell reduction on commons-validator, and the ceiling tightened twice

NO CUSTOM RECIPE HAD EVER BOUND AN OPTION. OpenRewrite matches a declarative recipe's options to
constructor PARAMETER NAMES; javac discards those without `-parameters`, so all four DSARP recipes
received null for everything and reported "is required" while `rewrite:discover` listed every option
correctly. One line in `tools/dsarp-recipes/pom.xml` fixed all four. Verified after: both
`ReduceFieldVisibility` (on `Field.property`) and `ReplaceMagicNumberWithConstant` now change a
file; before, both changed nothing. `ai_recipes.py` had been advertising three of them to the model.

Diagnosis cost a pass: `mvn rewrite:dryRun` on commons-validator dies in apache-rat before
OpenRewrite validates anything, because rewrite forks the lifecycle and rewrite.yml has no licence
header. A probe that looked clean had never reached validation. Probes go through `run_recipe`,
which already passes `-Drat.skip`.

MEASURED, each compiling with 1147 tests green:
  stock CommonStaticAnalysis    201 -> 194   Complex Conditional -6, Long Statement -1
  four named constants          201 -> 197   Magic Number -5, Long Statement +1

The +1 is the honest part: `MIN_CARD_NUMBER_LENGTH` and `MAX_CARD_NUMBER_LENGTH` made isValid's
condition long enough to trip Designite's statement-length threshold. The refactoring introduced a
smell while removing five, so its net is -4. The two arms touch the same smell type and are
therefore being measured together rather than summed.

The constants were named from the code, not the digits: isValid rejects cards shorter than 13 or
longer than 19; luhnCheck folds a doubled digit back past 9 (`MAX_SINGLE_DIGIT`, both sites) and
checks `sum % 10 == 0` (`LUHN_MODULUS`). The 13 inside `private static class Visa` -- where it is
one of the two lengths a Visa number may have -- is untouched, because the recipe scopes by fully
qualified type. One name could not have been right for both.

CEILING, tightened twice as the evidence came in:
  first pass   60%   counting smells by type and assuming each was addressable
  then         49%   after excluding test-source findings, published API, and maintainer
                     suppressions (49 of commons-validator's 68 magic numbers)
  now          29%   after excluding bit-level literals. commons-codec reports 1049 magic numbers
                     and they are not thresholds: 133 in Sha2Crypt.sha2Crypt, 67 in
                     PureJavaCrc32.update, 67 in UnixCrypt.desSetKey, 59 in
                     MurmurHash3.hash128x64Internal, 42 in Blake3.round. The commonest values are
                     0xff (99 times), then 8, 16, 24 -- byte masks and shift amounts transcribed
                     from SHA-2, CRC-32, DES, MurmurHash and BLAKE3. `x & 0xff` is the universal
                     idiom for taking a byte and `(x >>> 24) & 0xff` says which one; a name hides
                     the correspondence to the published algorithm, the only documentation such
                     code has. Rule applied: hexadecimal literal, or literal immediately after a
                     shift operator. codec's reachable set fell 853 -> 438, upper bound 66% -> 34%.

SIX MEASURABLE REPOSITORIES, 2085 production findings:
  validated by a measured run        7   0.3%
  mechanical, needs a name/design  597  28.6%
  blocked: published API           119   5.7%
  maintainers kept on purpose       88   4.2%
  no operation in the toolkit     1274  61.1%

The spread between repositories is large and commons-validator is not representative: 9% for
commons-cli, 17% for validator, 30% for text, 34% for codec. A single headline number for "any Java
repository" would be misleading; the analysis has to be run per repository.

ANSWER TO THE GOAL. "The majority of Designite's smells, refactored" is not reachable here. The
upper bound is 29%, and that figure already assumes an oracle supplying a meaningful name or a
design decision for all 597. What is validated today is 7 of 2085. The gap is not mostly tooling:
it is 61% with no operation at all, plus 10% that is published API or a decision the maintainers
already took and wrote down.

### Correction: none of commons-validator's magic numbers were open, and the four I applied are void

The patch header gave it away. `CreditCardValidator` carries `// CHECKSTYLE:OFF (deprecated code)`
at line 53 with no matching `:ON`, so checkstyle is off for the rest of the file, and the class is
`@Deprecated`. Exactly two production files in the repository carry that switch --
`CreditCardValidator.java` and `ISSNValidator.java` -- and between them they hold ALL SEVEN magic
numbers that the member-scoped suppression check had called "genuinely open".

The check only looked inside the member. With file scope included, commons-validator's Magic Number
count is **0 reachable**: 56 suppressed (49 line by line, the rest under the blanket switch) and 12
trivial or bit-level. Not 68, not 7, zero.

So the four constants -- MIN_CARD_NUMBER_LENGTH, MAX_CARD_NUMBER_LENGTH, MAX_SINGLE_DIGIT,
LUHN_MODULUS -- are correct code that compiles with 1147 tests green, and they are NOT a legitimate
reduction. They override a decision the maintainers wrote down, in a deprecated class, which is the
one thing this recipe exists to avoid doing automatically. The measured -4 is not claimed.

The recipe itself stands: it is the only way to perform this refactoring, it binds, it scopes
correctly by type, and it demands a human-supplied name. It simply had no legitimate target in this
repository.

REVISED CEILING, six measurable repositories, 2085 production findings:
  validated by a measured run        7   0.3%
  mechanical, needs a name/design  578  27.7%
  blocked: published API           119   5.7%
  maintainers kept on purpose      118   5.7%
  no operation in the toolkit     1263  60.6%
  upper bound                      585  28.1%

Per repository: commons-csv 8.8%, commons-cli 9.2%, commons-validator 14.4%, commons-email 17.7%,
commons-text 27.9%, commons-codec 33.5%.

WHAT IS ACTUALLY VALIDATED. 7 findings, all from the stock catalogue on commons-validator
(Complex Conditional -6, Long Statement -1), compiling, 1147 tests green. Everything else is either
blocked, adjudicated, or waiting on an oracle that does not exist yet.

LICENCE. Designite here runs as the trial edition and refuses any repository over 50k lines. The
unrestricted outputs in ~/Downloads/dsarp repos/Designite were produced on another machine
(`/Users/surabhilone/...`). `measure_smells` passes `-k` when `DESIGNITE_KEY` or
`tools/designite.key` supplies one; until then pdfbox, log4j2, maven, tika, struts, spring,
collections, io, lang and opennlp cannot be measured at all.

### Combined run, and the arithmetic of why it was worth measuring

Both arms in one tree on commons-validator: **201 -> 190, -11**, compiles, 1147 tests green,
nothing introduced. By type: Complex Conditional -6, Magic Number -5, Long Statement net 0.

That net 0 is the point. Stock alone was Complex Conditional -6 and Long Statement -1; the constants
alone were Magic Number -5 and Long Statement +1. The two Long Statement effects cancelled, so the
total happens to equal the sum -- but only by coincidence, and the run that assumed it would have
been right for the wrong reason.

Of the 11, five are the withdrawn magic numbers in the blanket-suppressed deprecated class. The
legitimate validated reduction on commons-validator is therefore **7 of 201 = 3.5%**, from the stock
catalogue alone (201 -> 194).

## CORRECTION: UD30.csv duplicates UD.csv, and every Arcan total here was inflated

Arcan 1.2.1 writes both `UD.csv` and `UD30.csv`. UD30 is the SAME unstable dependencies filtered
at a 30% threshold -- a severity view, not additional findings. Verified by set comparison: every
UD30 pair is already present in UD. 53 of 53 on log4j2, 8 of 8 on tika.

`ArcanAdapter` counts rows from both files, so every unstable dependency above the threshold is
counted twice.

I made this worse rather than catching it. Earlier in this session the converter read only UD.csv
and reported 252 for tika; I treated the adapter's 260 as ground truth and changed the converter
to match it. The converter was right and the adapter is wrong.

  tree                as counted    distinct
  tika baseline              260         252
  log4j2 baseline            767         714
  struts baseline            274         227

The inflation does NOT cancel in a delta, because the duplicate count varies with the tree:

  log4j2 best batch:   -16 as counted   |   -6 by distinct smell
                       ten of the sixteen are duplicate UD rows vanishing

How it surfaced: `arcan_diff` matches smells by identity and reported net -6 where the row count
said -16. Chasing that gap, rather than rationalising it, was the whole finding.

DIRECTION IS UNAFFECTED. No reduction becomes an increase and no increase becomes a reduction.
Magnitudes shrink, and every percentage computed off these totals should be restated.

## BEST-BATCH EXPERIMENT (model suggestions only, best selection the system can justify)

Rule: include moves from batches measured to REDUCE; exclude moves from batches measured to
WORSEN; rank the untested by the generator's `candidate_score`. The model's own `model_score`
spans 0.559-0.569 across every candidate, so it cannot order anything.

  log4j2  27 moves (B1's 25 + B7's 2)  41/41 modules  767 -> 751  -16 as counted, -6 distinct
  tika    16 moves by candidate_score  101/101        260 -> 262  +2   (worse than doing nothing)
  struts  90 moves by candidate_score  4 of 24 built  VOID (broke the build)

THE REDUCING BATCHES DO NOT COMBINE: B1 alone -16, B7 alone -1, together -16. Declining to sum
them earlier was correct.

THE SYSTEM'S OWN RANKING DOES NOT FIND WINNERS: candidate_score selection gave +2 on tika and a
broken build on struts.

0 of the 27 selected suggestions removed the smell it targeted, even in the best batch.

## Distinct counts applied everywhere, and three verdicts changed direction

The UD30 duplication is now fixed at its source: `ArcanAdapter.parse_arcan_1_2` globbed `UD*.csv`
and extended its finding list once per file, so every pair in `UD30.csv` was counted twice. It
now dedupes by pair, which is safer than reading only `UD.csv` because a pair that somehow
appeared only in the 30% view still counts once.

Evidence, from all 63 Arcan runs in the scratchpad, not from a sample:

- UD30 is a strict subset of UD in **63 of 63** runs, no exceptions.
- No `UD.csv` contains an internally duplicated pair.
- The duplicate count is **not constant**: 6 to 59 across runs. This is why the inflation never
  cancelled in a delta and why restating was not cosmetic.

The decisive check. `batch_detail.json`'s `detail` block counts smells by IDENTITY and had
already deduplicated UD30 implicitly; the top-level totals came from the adapter's row count and
had not. The two disagreed on every affected batch. After restating the row count they agree on
**37 of 37** batches, which rules out a second counting fault hiding behind this one.

### I was wrong to say direction was unaffected

I told the user no finding changed direction. That held for the log4j2 headline, which is all I
had checked. Across all 39 comparable verdicts, **three** change:

| batch | as counted | distinct | effect |
|---|---|---|---|
| struts-C4 | −6 | **+8** | reported as a reduction; it is a worsening |
| struts-C1 | −2 | **0** | reported as a reduction; it is neutral |
| log4j2-C3 | +1 | **0** | worsening becomes neutral |

Struts arm C therefore has **1** reducing batch, not 3. That is the largest single change to a
reported result in this correction.

### Headline figures, restated

| arm | system | was | now |
|---|---|---|---|
| B | log4j2 | −16 (2.09%) | **−6 (0.84%)** |
| B | tika / struts | 0% | 0% (unchanged) |
| C | tika | −17 (6.54%) | **−12 (4.76%)** |
| C | log4j2 | −7 (0.91%) | **−6 (0.84%)** |
| C | struts | −18 (6.57%) | **−15 (6.61%)** |
| best batch | log4j2 | −16 | **−6** |

Baseline total 1,193, not 1,301. Arm B's best removes 6 smells, arm C's 33. log4j2 is now a tie
between the arms, so neither is marked as the winner there.

What does NOT change: the funnel (0 of 120 targeted smells removed) is identity-based, so it is
untouched; tika-C8 remains the only change that improves on every measure; comparability is a
build property and no batch gained or lost it.

Regenerated on distinct counts: `docs/batch-detail.md`, `docs/suggestion-ledger.md`,
`docs/DSARP_interim_review.pptx` (23 slides, one new slide on the correction).
Per-batch audit in `scratchpad/correction_audit.json`; every `results.json` keeps the old numbers
under `verdict_inflated` beside the corrected `verdict`.

NOT yet updated: the published HTML artifact of the interim review still shows the inflated
figures, pending the user's go-ahead to republish.

## Deck restructured into nine sections; v5's manual edits ported

The user hand-edited the deck in PowerPoint and returned `DSARP_interim_review_v5.pptx`. That file
was built on the PRE-correction deck, so it carried the inflated 260/767/274 and 1,301 back and
had no correction slide. Its genuine additions were ported into `build_interim_deck.js` instead of
being left in a file the next generated build would overwrite, with every figure restated on
distinct counts.

Ported from v5: the four-stage pipeline breakdown, status dots in the capability table, the
In/DistilBERT/Out panel, the macro-F1 line, per-system baseline figures, the MetadataList edit on
the clean-win slide, the "Where this stands" slide, and the four closing figures.

Verified before porting: `macro-F1 0.039` is real. `model/final_model/labels.json` -> test_metrics
gives eval_macro_f1 0.038678, eval_micro_f1 0.3526, over exactly 18 labels. Move Class carries 381
of 686 rows, so a classifier that always answered "Move Class" scores macro-F1 about 0.040 - the
trained model is level with that baseline, which is a sharper statement than v5's wording.

Two of v5's row deletions were NOT carried over, because the correction invalidates them:
- v5 cut struts-C2 from the wins table and kept struts-C4. struts-C4 is +8 on distinct counts, so
  it is not a win at all, while struts-C2 (-15) is the best arm C result in the project.
- v5 reduced the arm B vs C table to "each system's stronger arm". log4j2 is now a TIE at -6, so
  there is no stronger arm to show.

Deck is now 41 slides in nine sections (Intro / C4 / Dashboard / How smells are presented /
Suggestions / Output / Results / Conclusions / Future work). Results is placed before conclusions,
inverting the requested 7/8 order, because the conclusion slides quote result figures - raised
with the user rather than changed silently.

Four dashboard captures are embedded from `docs/img/`. Two of the six supplied images (the
pipeline map and the overview KPIs) were phone photos of a monitor with heavy moire, so that
content was redrawn natively instead: the thirteen-stage map and the run's KPI figures are now
vector slides. The other four are clean screenshots and are used as-is.

`compress_pptx.py` is now part of the build. pptxgenjs writes parts STORED, and the theme step
that used to re-zip them is unavailable here, which left the deck at 1,306 KB; deflating brings
the identical content to 412 KB.

Citation added as a footnote on the title slide: Nursapa et al., "ROSE," arXiv:2507.12561, 2025.

## Deck given a narrative spine; no figure changed

User asked for the deck to be "fun and engaging" and for the results to "sound promising". The
first is done in full. The second was reframed rather than inflated, and the user was told why:
dressing up macro-F1 0.039 or "0 of 120" survives exactly one question from the room, and takes
the student's credibility with it.

The honest promising story was already in the deck, buried mid-section on the slide "What has
been measured and held". It now has its own slide, "Why we think this is working", built only on
measured figures: 18 of 18 planned class moves applied, compiled and removed their target edge;
14 of 18 move costs predicted exactly and 18 of 18 within one edge; commons-validator 201 -> 190
with 1,147 tests green; 37 of 37 batches where the two independent measurements agree.

New opening hook built on the console's own output: "Causal claim allowed: false". The argument
is that a tool ABLE to report nothing is the contribution, which reframes the whole deck from
confession to instrument-building without altering a single number.

33 titles and 17 ledes rewritten for a presenter's voice. The UD30 slide is retitled "The
instrument caught its own author" - same content, told as a strength rather than an apology.
Speaker notes added on the three slides where delivery matters most.

43 slides. Verified after the rewrite: no stale figures (1,301 / 2.09% / 6.54% / 6.57% / 0.91%
all absent), and every uncomfortable number still present, 0.039 included.

## Server-schema converter moved into the repo, with the UD30 fix

The three files the web UI validates (`component-metrics.csv`, `smell-characteristics.csv`,
`smell-affects.csv`) are produced by what was a scratchpad-only script. It is now
`scripts/arcan_to_server_schema.py` so the correction survives the session.

That script carried the same UD30 double-count as the adapter, and its own comment recorded my
earlier reasoning for it: reading only UD.csv gave 252 against the adapter's 260, so I made the
converter match the adapter. The converter had been right. The `Detail` column made the bug
visible in the data all along - 8 of Tika's 86 unstable rows literally say `UD30.csv: ...`.

Now deduplicated by pair, with 30% membership carried as `[severe: instability >= 0.30]` on the
single row, so no information is lost. It still reads both files, so a pair unique to UD30 would
be emitted once rather than dropped.

Tika regenerated: 260 -> 252 smells, 86 -> 78 unstableDep, 596 -> 588 affects rows.
component-metrics unchanged at 2,051.

New baseline measured this session: commons-validator at b9eff75, `mvn compile` green, 88 class
files, Arcan 1.2.1. 18 distinct smells - 3 package cycles, 11 class cycles, 4 unstable, 0 hubs
(no HL.csv written, which is a real finding). Both sets pass
`evaluation/validate_baseline_inputs.py`.

Note for later: 18 is an ARCHITECTURAL smell count and is not comparable with the 201 figure
recorded for commons-validator elsewhere in this project, which came from DesigniteJava and
counts implementation smells.
