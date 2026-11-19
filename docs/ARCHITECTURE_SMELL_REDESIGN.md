# Redesign: what to build next for verified architectural-smell reduction

Audit date: 2026-11-01. Covers `shimoriki/DSARP-OpenRewrite` at `36b6e97`, `dsarp-project` on
all branches and all eight sibling worktrees. Experiment target: Apache Log4j2 at
`4f474b32751f4ccad67424ca585612584440cd63`.

## 0. Verdict

**The pipeline in the brief already exists.** The branch `claude/infallible-wescoff-ee351b`
(`f82d2ca`) implements detect, bytecode graph, arithmetic move prediction, Spoon and OpenRewrite
execution, ordered gates, and identity-based smell comparison. It has been run on pdfbox, log4j2
and tika. A rewrite would throw away 174 commits of hard-won negative results.

**So this is a redirection, not a replacement.** Three changes matter:

1. **Stop attacking giant SCCs. Dissolve small ones.** The project's headline "no cycle was ever
   dissolved" is a result of what the planner aims at. Simulation on Log4j2 predicts one single
   move eliminates a whole size-2 SCC, and greedy Move Class shrinks the 10- and 15-package SCCs
   to 6 and 8. **This is a prediction. Nothing has been applied.** It is the first experiment to run.
2. **Finish the instrument.** No API report, no placebo control, no generated regression rule, no
   EvoSuite, and per-module Arcan runs that miss cross-module findings.
3. **Stop three activities the evidence has closed:** label classification, package splitting,
   and a sixth smell-delta ranker.

**The brief's success rule is amended (decided 2026-11-01).** "The target smell disappears or
shrinks" cannot be met on giant SCCs by anyone, including the experts in Arcelli Fontana's package.
Section 9 keeps the brief's evidence levels but defines Level 4 against named units.

### Evidence labels

- **[M]** measured in this audit; scripts in `research/log4j2_feasibility/`.
- **[R]** recorded in project docs or status logs; numbers not re-run here.
- **[C]** read directly in code.
- **[P]** read from the primary page or abstract.
- **[S]** seen in a search snippet only.
- **[U]** background knowledge, unverified here. Check before citing.

### Limits of this report

- A targeted scan, not a systematic review. Most papers were read at abstract or snippet level.
  Unknown fields mean "not verified", not "absent".
- Scores and probabilities are engineering judgment, not statistics.
- **No pipeline code was written, and no Arcan, Maven verify, test run, or refactoring was executed
  here.** Only `jdeps` over a compile, plus Python simulation.
- Project numbers marked [R] were not re-derived. Some were corrected repeatedly in the project's
  own history, so quote them only with their date and metric.

Note: `agent-architecture-audit` targets LLM wrapper stacks. Most of this system is not one, so the
skill supplied the severity format only.

---

## 1. Deliverable 1: audit of what exists

### 1.1 Four lineages

| Lineage | Where | State | Role |
|---|---|---|---|
| DSARP Studio | `agentic-refactoring-agent` (`8f55c1d`); this worktree, `anische-dataset-training-data-a203c3` | Stopped July 2026 | LLM suggestions + HGRS review. Edits no code |
| DSARP-OpenRewrite | GitHub, separate repo | Stopped August 2026 | DistilBERT labels + `generate_recipes.py` + Arcan compare |
| Evidence-based agent | `feature/arcan-designite-openrewrite-loop` (`ce64ae6`); main checkout, `ai-agents-refactoring-3afbab`, `clever-bassi-39cae2`, `dsarp-agent-loop-setup-45a511`, `goose-architecture-diagrams-08b1a8` | August 2026 | Closed loop, multi-agent |
| Evidence-based agent, latest | `claude/infallible-wescoff-ee351b` (`f82d2ca`) | 13 Oct 2026, 79 commits past `ce64ae6` | **The real baseline** |

### 1.2 Work that exists in only one worktree [C]

| Worktree | Delta | Status |
|---|---|---|
| `infallible-wescoff-ee351b` | 84 commits not on `origin/feature/...` | **Local only** |
| `clever-bassi-39cae2` | Merged-root Arcan: `dsarp/tools/arcan_runner.py`, `tests/test_arcan_merged_stage.py` | **Uncommitted, and absent from `f82d2ca`** |
| `ai-agents-refactoring-3afbab` | Spoon agent, recipe option tests, `docs/worklog/` | **Uncommitted.** A later form is in `f82d2ca`, but files differ, so check before discarding |
| `agent-workflow-breakdown-61430c` | `7a8490e`, `dd188e8`: iteration in validator, `docs/AGENT_WORKFLOW.md` | Committed, unmerged |
| `dsarp-agent-loop-setup-45a511`, `goose-...`, `anische-...` | None | Clean |
| `infallible-wescoff-ee351b` | Stray empty directory `tools$d` | Shell-escape debris |

**Risk:** months of results sit on one disk. Push is the user's call, but it should happen.

### 1.3 Current architecture (`f82d2ca`) [C, R]

```text
repo -> compile_repo (mvn/gradle, module-drop handling)
     -> Arcan 1.2.1 per module; Designite Pro 2.9.1 (source)
     -> ArchUnit snapshot + jdeps class graph (two independent bytecode readers)
     -> move_planner.plan_moves: single-carrier in-cycle edges, relabel class, re-derive packages
     -> Spoon or OpenRewrite in a copy
     -> verification/gates.py: before_apply, after_apply (residual FQN), structural, behavioural
     -> experiments/{edge_measure,arcan_diff,suggestion_ledger}.py
```

The brief's 15 audit points for the transformer path are answered in 1.5. Coverage is 13 of 15 smell
types with a planner (`docs/coverage.md`), but only Move Class and inversion are verified on bytecode.

### 1.4 What is measured [R]

| Claim | Number | Source |
|---|---|---|
| Planned moves, 3 repos | 18 applied, 18 built, 18 target edges gone, **14 accepted by tests** | status, 2026-09-23 |
| Inversion on same edges | 1 of 18 | same |
| Move cost prediction | Exact 14/18, within two 18/18 | viva bank (one slide said "within one"; **wrong**, fix it) |
| Transformer suggestions | 1,282 sampled, 473 concrete, 354 attempted, 120 comparable, **0 removed target** | `suggestion-ledger.md` |
| Model quality | Macro-F1 0.0387 vs always-`Move Class` 0.040 | status, viva bank |
| Composite extraction | 4 applied, 2 compiled, 0 accepted | status, 2026-10-01 |
| Package split | 77 of 78 predicted worse; 0 of 4 measured | status, 2026-10-02 |
| Five selection attempts | All failed held-out | `negative-results.md` |
| Designite reachable ceiling | 28.1% of 2,085; 0.3% validated | status |
| Expert trees (Arcelli Fontana) | Neither compress nor jeromq dissolved a cycle | status |

`docs/TECHNICAL_REPORT.md` still leads with LORO 0.978. That number measures agreement with weak or
historical labels and is contradicted in spirit by the ledger. It must not be presented as the
project's result.

### 1.5 DSARP-OpenRewrite: the brief's 15 points

1. **Inputs.** Three Arcan CSVs, Git URL, commit. [C]
2. **Training.** `arcan_matched_dataset_builder.py`. `--reverse` then first-N keeps the *oldest* 500
   keyword-matched commits per repo. Keeps rows marked improved. [C]
3. **Model.** `distilbert-base-uncased`, multi-label, `MAX_LENGTH = 256`, lr 2e-5, 5 epochs, BCE
   weighted up to 10. [C]
4. **Schema.** `"Label (score) | ..."`, unconditional top 5. [C]
5. **Smell to input.** Flat sentence of names and numbers. No edges, no source. [C]
6. **Labels.** RefactoringMiner types filtered to 18, then by support. [C]
7. **Label to refactoring.** Only `Move Class`, at any rank (`generate_recipes.py:287-294`). [C]
8. **Executable.** `ChangeType`, same module. [C]
9. **Not executable.** Everything else lacks parameters. Class-level smells stop at "affected packages
   not present": 346 of 717 rows. [M]
10. **Recipes.** String-templated YAML. [C]
11. **Validation.** `./mvnw -DskipTests verify` per candidate; tests once on the aggregate. [C]
12. **Arcan compare.** Arcan 1.2.1 on merged `target/classes`; exact-set equality. [C]
13. **Evaluation.** Ranking metrics, build status, aggregate delta, `causal_claim_allowed`. [C]
14. **Log4j2 assumptions.** `FileSize` facade, hard-coded packages, tests, module lists, known Spring
    failure. [C]
15. **Maven assumptions.** `mvnw`, `target/classes`, macOS `Contents/Home`, `.venv/bin`. [C]

How it resolves code: regex `package`, `import`, first `class X` anywhere including Javadoc. Direct
imports only. Reciprocal pairs only. No labels with parameters. `ChangeType` hard-coded.

---

## 2. Deliverable 2: failure analysis of the transformer path

### 2.1 New findings from this audit, ranked

The project's ledger already proves the chain produces nothing (0 of 120). These explain the mechanism.
They apply to DSARP-OpenRewrite as committed.

**Critical**

1. **Candidates are never checked for effect.** Bytecode simulation of the current generator's 220
   in-scope candidates: reciprocal pairs fall for 24 (10.9%), **rise for 59 (26.8%)**. SCC edges fall
   for 29, rise for 84. Worst: `Configuration -> ...core.script` adds 6 pairs. [M]
2. **`is_public` is constant.** Java forbids importing a non-public top-level type across packages, so
   every resolved candidate is public: 237 of 237 `high_public_api`. The gate is impassable except for
   the hard-coded `FileSize`, which is why docs show 39 of 40 in `manual_review`. The sort key does
   nothing, and the "model-driven" result was a hand-registered case. [M, C]
3. **`aggregate_counts_comparable` cannot be false in real runs.** `summarize()` hard-codes
   `"version": "1.2.1"` and the configuration string, so the check compares two constants. Unit tests
   pass only because they inject different values. [C]
4. **`causal_claim_allowed` ignores outcome and attribution.** True if any validated change exists.
   Candidates apply as one aggregate. [C]
5. **Per-candidate validation skips tests.** `validate_openrewrite_candidates.py:224`. [C]

**High**

6. **Feature shift.** Training `Severity` and `ATDI` are homemade (`len(affected)` for cycles). Inference
   receives real Arcan values under the same names. [C]
7. **Non-causal labels.** Text overlap by simple name, and "improved" means the membership signature
   changed at all, including growth. [C]
8. **Regex identity failure.** 212 of 2,268 parsed types misnamed, such as `to`, `for`, `is`. 65 FQNs
   collide across modules. [M]
9. **Regex edge loss.** 603 package edges vs 899 in bytecode; 307 bytecode-only. [M]
10. **Baseline grep.** `run_expected_spring_failure` accepts any failing log containing one known test. [C]

### 2.2 Where information is lost

| Step | Lost |
|---|---|
| Arcan export | Edges and direction: `smell-affects.csv` holds membership only |
| CSV to text | Structure; 256 tokens against a median of 11 packages per cycle, max 39 [M] |
| Model to label | All parameters. Output is near constant [R] |
| Label to candidate | Causality, access rules |
| Candidate to recipe | Intent: `expected_removed_edges` is never recorded |
| Recipe to verdict | Per-candidate effect |

### 2.3 By category

- **ML/data:** 686 rows, 18 labels, non-causal, domain shift.
- **Representation:** no causal edges.
- **Candidate generation:** reciprocal-only, no simulation, wrong objective.
- **Transformation engine:** not the failure. Backends agree exactly once integrated [R].
- **Dependency resolution:** regex.
- **Build/environment:** Maven and macOS only.
- **Evaluation:** tautological comparability, aggregate attribution.

### 2.4 Four separate questions

| Question | Best current answer |
|---|---|
| Prediction quality | None above baseline. Macro-F1 0.039 [R] |
| Executability | Move Class yes; inversion mostly no; 36.9% of suggestions concrete [R] |
| Behavior preservation | 14 of 18 pass tests; compile alone is misleading (Tika ServiceLoader) [R] |
| Smell reduction | Named edges yes. Target smells 0 of 120. Cycles: not yet achieved |

---

## 3. Core question: is a model needed?

**No.** This is now measured, not argued: arithmetic prediction beats every fitted model the project
tried. The brief's three architectures:

| Criterion | A: deterministic | B: hybrid ranking | C: agentic |
|---|---|---|---|
| Reproducibility | Exact | Candidates exact | Low |
| Candidate validity | By construction | By construction | Fabrication reported in Pandini package [P]; 0 of 6 usable with `qwen2.5-coder:3b` [R] |
| Design sense | None: top move is `StatusLogger -> spi` [M] | Could help | Could help |
| Evidence | 18 of 18 edges removed [R] | Five selection failures [R] | SmellBench: best 47.7%, up to 140 smells introduced, Python, cycles excluded [P] |

**Decision:** stay on A. B is justified only for design-sense veto, and only pre-registered. C stays a
baseline arm. Project evidence agrees with prior work on *enumerate-and-pick*.

---

## 4. Deliverable 3: prior-work landscape

The project's `COUNTERMEASURES.md` and `TOOLING.md` already cover JMove, JDeodorant, SAFEREFACTOR, MORE,
ROSE, RefAgent, EvoSuite and the LLM empirical studies. These are the additions from this audit.

### 4.1 Peer-reviewed or formally published

| Work | Year, venue | Approach | Edits code? | Relevance | Basis |
|---|---|---|---|---|---|
| Pandini, Martini, Videsjorden, Fontana. *An Exploratory Study on Architectural Smell Refactoring Using Large Languages Models* | 2025, ICSA-C 462-471, DOI 10.1109/ICSA-C65153.2025.00070 | Prompts, RAG, local vs cloud, on cycles | Suggests | Closest LLM work; Arcelli Fontana's group | [P] |
| Kuo, Hsieh, Lin, Lin. *The Study on Software Architecture Smell Refactoring* | 2024, IJSI 12(1), DOI 10.4018/IJSI.339884 | Cause analysis for CD, UD; priority metric; cost-effective sequence; simulation | Suggests | Same concept at small scale | [S] |
| Abdeen, Ducasse, Sahraoui, Alloui. *Automatic Package Coupling and Cycle Minimization* | 2009, WCRE, DOI 10.1109/wcre.2009.13 | Simulated annealing over class-package moves | Model-level | **Closest match to what `plan_moves` lacks: multi-move search** | [S] |
| Shah et al. *On the Automation of Dependency-Breaking Refactorings in Java* | c. 2013; thesis Massey 10179/5176 | Move class, type generalization, service locator, inlining | Yes per thesis | **Strongest prior baseline.** Adds service locator and inlining, which address exactly the inversion refusals | [S] |
| Oyetoyan et al. *A Decision Support System to Refactor Class Cycles* | 2015 | Reachability-set metric | Recommends | Candidate pruning | [S] |
| Mkaouer et al. *Many-Objective Software Remodularization Using NSGA-III* | 2015, TOSEM, DOI 10.1145/2729974 | Sequence search | Model-level | Reference for search | [S] |
| Ouni et al. *Multi-Criteria Code Refactoring Using SBSE* | 2016, TOSEM, DOI 10.1145/2932631 | Multi-objective | Model-level | Objectives | [S] |
| Lin et al. *Interactive and Guided Architectural Refactoring with Search-Based Recommendation* | 2016, FSE, DOI 10.1145/2950290.2950317 | Refactoring Navigator | Recommends | Target-design guidance | [S] |
| Praditwong, Harman, Yao | 2011, TSE 37(2) | Multi-objective clustering | No | Concept | [S] |
| Mitchell, Mancoridis, Bunch | 2008, Soft Computing 12(1) | Search over partitions | No | God Component later | [S] |
| Terra et al., ArchFix; DCLfix | 2012 CSMR, 2013 SPE; arXiv 1506.07589 | 32 repair recommendations | Recommends | Operator catalog | [S] |
| Sas, Avgeriou, Arcelli Fontana; ASTracker | 2019, ICSME | Smell identity across versions | No | `arcan_diff` could reuse the idea | [S] |
| Arcelli Fontana et al., Arcan | 2017, ICSA-W | Graph detection from bytecode | No | Oracle | [S] |
| Pawlak et al., Spoon | 2015, SPE | AST library | Library | In use | [S] |

### 4.2 Preprints and artifacts

| Work | Finding | Basis |
|---|---|---|
| Dinu, Mihăescu, Rebedea. *SmellBench*, arXiv 2605.07001 | scikit-learn; PyExamine re-run as oracle; 63.1% false positives; best 31/65; 0-7 of 14 Unstable resolved; cycles excluded; Zenodo 19247588 | [P] |
| Pandini, Goknil. Zenodo 19819717 | Two-step: LLM picks a dependency, then refactors. Claude 3.5 Sonnet and Qwen2.5-Coder; Arcan v2.9.4. Qwen fabricated classes. Numbers not on page | [P] |
| ROSE, arXiv 2507.12561, ESEM 2025 | 96.9% accuracy, 3 classes; no removal measured | [P] |
| Feng et al., arXiv 2306.10599 | Two-class cycle untangling patterns over 18 projects; design context matters. PDF unreadable here | [S] |
| MANTRA, arXiv 2503.14340 | Method-level, 82.8% compile and test vs 8.7% raw | [S] |
| RefAgent, arXiv 2511.03153; Horikawa, arXiv 2511.04824; *Ripple*, arXiv 2610.24790; ArchGuard-APR, arXiv 2610.33853 | Agents stay low-level; compile and test alone are insufficient; ArchGuard pilot 0/2 | [S] |

### 4.3 Direct answers

- **Remodularization to source?** Yes, at Move Class level: a partition is a class-to-package map.
- **Concrete recommenders?** JDeodorant, DCLfix, Abdeen. Not ROSE or the model.
- **Synthesis, SMT, GNN, RL for cycle removal?** Nothing found in this scan. Weak evidence of absence.
- **Can search optimize smells directly?** Yes, and it is practical now, since `move_effect` costs
  seconds. Test failures stay as gates. `TOOLING.md` said wait until a predictor makes evaluation cheap;
  **that condition has been met**, because arithmetic prediction is that predictor.

---

## 5. Deliverable 4: feasibility matrix

1-5, effort 5 = cheapest. Apache suitability is folded into scale, CI into automation, so weights
total 100%: AR 20, Java 10, Auto 15, Concrete 15, Verify 15, Scale 10, Repro 10, Effort 5.

| Approach | AR | Java | Auto | Conc | Ver | Scale | Repro | Eff | Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DSARP `f82d2ca` + small-SCC search | 5 | 5 | 5 | 5 | 5 | 4 | 4 | 4 | **4.75** |
| DSARP `f82d2ca` as is | 4 | 5 | 5 | 5 | 5 | 4 | 4 | 5 | 4.60 |
| SmellBench protocol | 4 | 1 | 5 | 3 | 5 | 3 | 4 | 3 | 3.70 |
| Shah dependency-breaking | 4 | 5 | 4 | 4 | 2 | 3 | 2 | 2 | 3.40 |
| MANTRA pattern | 1 | 5 | 5 | 5 | 3 | 3 | 3 | 2 | 3.25 |
| Pandini two-step LLM | 5 | 5 | 2 | 3 | 1 | 2 | 4 | 4 | 3.20 |
| DSARP-OpenRewrite | 3 | 5 | 3 | 2 | 3 | 3 | 2 | 5 | 3.05 |
| RefAgent | 1 | 5 | 5 | 4 | 3 | 3 | 3 | 2 | 3.00 |
| Refactoring Navigator | 4 | 5 | 2 | 4 | 2 | 3 | 2 | 3 | 2.95 |
| NSGA-III | 3 | 5 | 2 | 4 | 2 | 3 | 2 | 2 | 2.90 |
| JDeodorant | 2 | 4 | 4 | 5 | 1 | 2 | 3 | 2 | 2.90 |
| Abdeen annealing | 4 | 3 | 1 | 4 | 2 | 3 | 2 | 3 | 2.80 |
| DSARP Studio | 4 | 4 | 1 | 2 | 1 | 3 | 4 | 5 | 2.75 |
| ArchFix, DCLfix | 3 | 5 | 1 | 4 | 1 | 3 | 2 | 2 | 2.60 |
| Kuo 2024 | 4 | 3 | 1 | 3 | 2 | 2 | 2 | 2 | 2.50 |
| Bunch | 3 | 4 | 1 | 3 | 1 | 4 | 2 | 3 | 2.50 |
| ROSE | 3 | 5 | 1 | 1 | 1 | 4 | 3 | 3 | 2.40 |

Rows for tools not inspected rest on published descriptions.

---

## 6. Deliverable 5: ranked prior solutions

| Rank | Approach | Source | Solves | Usable? | Effort | Usefulness | Major risk | Tier |
|---|---|---|---|---|---:|---|---|---|
| 1 | `move_effect` + SCC-scoped greedy or beam | This repo + Abdeen | Multi-move planning | Yes | Low | Very high | Moves are public API | A |
| 2 | Service locator, inlining | Shah | Inversion refusals (annotation, constructs, static) | Ideas | Medium | High | Source availability unverified | A/B |
| 3 | Re-run oracle + false-positive triage | SmellBench | Reporting | Protocol | Low | High | Python tool | A |
| 4 | SAFEREFACTOR with EvoSuite | `TOOLING.md` | Behavior gap | Yes | Medium | High | Generated oracle weakness | A |
| 5 | Pandini two-step | Pandini | Edge choice by LLM | Package exists | Low | Medium | Fabrication | B |
| 6 | Reachability metric | Oyetoyan | Pruning | Yes | Low | Medium | Class-level | B |
| 7 | Design-sense LLM veto | MANTRA reviewer shape | `StatusLogger`-type moves | Pattern | Medium | Medium | Sixth ranker failure | B |
| 8 | NSGA-III | Mkaouer | Pareto sets | Reimplement | High | Low to medium | Beam likely enough | C |
| 9 | Refactoring Navigator | Lin | Target design | Concept | High | Low | Needs target | C |
| 10 | ArchFix, DCLfix | Terra | Operators | Concept | Medium | Low | Needs rules | C |
| 11 | Bunch | Mitchell | God Component | Concept | High | Low now | Split is closed | C |
| 12 | Classifier: ROSE or DistilBERT | | Wrong problem | Yes | None | None | Consumes effort | D |

---

## 7. Deliverable 6: probability of success

Stages are conditional on the previous one; the last column is standalone.

| Approach | Concrete | Compiles | Tests | Target reduced | Scales |
|---|---|---|---|---|---|
| Single planned move, named edge | Very High | Very High | High (14/18 [R]) | Very High on edge | High |
| Small-SCC dissolve, 1-4 moves | High | High | Moderate | **Moderate** (one instance predicted) | Moderate |
| Inversion, unblocked edges only | Moderate | Low | High | Moderate | Moderate |
| Composite with placement check | Moderate | Moderate | Moderate | Low to moderate | Moderate |
| LLM veto over valid moves | High | Unchanged | Unchanged | Unchanged, cost or quality gain only | High |
| LLM patch writing | Moderate | Low | Low | Low | Low |
| Giant SCC dissolution | Very Low | n/a | n/a | Very Low: 156 edges and 1,164 classes on log4j2 [R] | n/a |
| Classifier | Very Low | n/a | n/a | Very Low | High |

---

## 8. Deliverable 7: research gaps and questions

| Component | Literature | Here |
|---|---|---|
| Detection | Mature | Yes |
| Cause analysis | Kuo, Oyetoyan | Yes |
| Search over moves | Abdeen, Mkaouer, on model | Single-step only |
| Source-level breaking | Shah | Move yes, inversion weak |
| Re-run oracle | SmellBench, Python | Yes, on Java |
| **Predicted vs observed, per candidate, on large Java, with named-edge verification** | **Not found** | **Yes** |
| **Whole-cycle dissolution with API-safe proof** | **Not found** | Not yet |

Realistic contribution: an **instrument**, plus a measured statement of what is reachable. The
project's own framing, "Causal claim allowed: false", is the strongest line it has. Do not claim "first"
without a systematic search.

Research questions:

- **RQ1.** How accurately does class-graph relabelling predict bytecode package edges after a
  refactoring, and what explains the residual?
- **RQ2.** What fraction of package SCCs in Apache Java systems can automated moves dissolve, as a
  function of SCC size, with tests intact?
- **RQ3.** What share of moves survives when binary compatibility is required?
- **RQ4.** Under identical gates, does any LLM role improve on deterministic planning per unit cost?
- **RQ5.** Do smell-count deltas exceed a placebo, and how do they relate to edge and participation
  measures?

---

## 9. Deliverable 15: verification, amended

The current `gates.py` order is right: cheap first, tests last, only tests can accept. Keep it.

### 9.1 Evidence levels

| Level | Meaning |
|---|---|
| 0 | Suggestion only |
| 1 | Graph relabelling predicts the effect |
| 2 | Concrete patch |
| 3 | Build, tests no worse; API result recorded |
| 4a | **Named edge** gone, in two bytecode readers |
| 4b | **SCC shrunk**: strict subset, no new cycle |
| 4c | **SCC dissolved** or Arcan target identity gone, Arcan agreeing |
| 5 | Confirmed by second detector or generated architecture rule |

Only 4a to 5 are success, always named by sub-level. **Never report 4a as "smell removed".** That
distinction is what the amendment protects: the brief's Level 4 alone would record 0 forever, or
tempt relabelling.

### 9.2 Algorithm

```text
baseline <- detect_merged(repo@commit)    # twice; abort if outputs differ
tests0   <- run tests -fae                # 3 times; quarantine flaky by test ID
placebo  <- pipeline with neutral edit    # delta must be zero
while budget remains:
    target <- next small SCC, else named edge
    plan   <- beam(move_effect, target)   # predicted before anything runs
    for step in plan:
        w <- copy(head); apply one move
        before_apply -> after_apply -> compile incl. tests -> comparable
        -> structural -> API -> behavioural
        any failure: reject with reason, delete w, replan
        record predicted vs measured
    if plan complete: re-detect; assign level; emit regression rule; head <- w
```

Rules:

- **Removed:** no post-state cycle contains all target members, on same module set.
- **Shrunk:** best match is a strict subset. Exact-set `arcan_diff` currently scores this as one
  removed plus one created; report it separately.
- **API:** japicmp on changed jars. A report, not a rejection gate: a binary break does not reject the
  candidate, but it is recorded per candidate and never hidden in a total.
- **Facade rule:** a facade left in `P` for a type moved to `Q` adds `P -> Q`. It is legal only if the
  target edge is `Q -> P`. `FileSize` satisfied this: 20 edges forward, 1 back [M].
- **Net:** `net_smell_reduction = removed - introduced`, by identity, distinct counts.
- **Rate:** `smell_reduction_rate = (baseline - final) / baseline`, always with placebo delta beside it.

---

## 10. Deliverable 9: recommended architecture

**Minimal.** `f82d2ca` plus merged-root Arcan, japicmp report, placebo arm, SCC-scoped planner.

**Research.** Plus EvoSuite on touched types, generated ArchUnit rules, Shah operators, second project
family, and pre-registered LLM veto.

**Ambitious.** Placement-aware composite extraction, public-API migration recipes for downstream
(`write_migration_recipe` exists), CI bot with human approval.

---

## 11. Deliverable 8: tool landscape

| Tool | Role | Input | Output | License | Status here |
|---|---|---|---|---|---|
| Arcan 1.2.1 | **Detector** | Bytecode | CSV | Not stated on wiki | Oracle. 100% precision, 63% recall per `TOOLING.md` [R] |
| Arcan current | **Detector** | Git | Not verified | Annual subscription; academic access not stated [P] | Pandini used v2.9.4; supplied CSVs may be newer |
| DesigniteJava Pro 2.9.1 | **Detector** | Source | CSV | Licensed here; analyzed 180,707 LOC [R]. GitHub edition Apache-2.0 [P] | **Keep separate; never merge counts** |
| Sonargraph | **Detector + rule checker** | Multi-language | Reports | Paid with free Explorer [P] | Not used |
| Structure101 | Structure tool | | | Bought by Sonar, 2024 [P] | Not used |
| SonarQube Architecture | **Rule checker** | | | Paid editions [P] | Not used |
| ArchUnit | **Rule checker**, here oracle | Bytecode | Test result, custom | Not verified | In use, `tools/dsarp-archunit` |
| jdeps | **Dependency extractor** | Bytecode | Text | JDK | In use |
| jQAssistant | **Graph + rules** | Bytecode, source | Neo4j | GPLv3; Gradle unconfirmed [P] | Skip: nothing it adds |
| CK | **Metrics**, not a detector | Source | CSV | Apache-2.0 [P] | Optional for RQs |
| PMD | Code rules | Source | Many | Not verified | Not architectural |
| JDeodorant | **Recommender** | Eclipse | IDE | Not verified | Skip |
| RefactoringMiner 3.1.4 | **Miner** | Git | JSON | Not verified | Keep for corpus only |
| japicmp, Revapi | **API validators** | Jars | Reports | Apache-2.0 [P] | **Absent. Add japicmp** |
| EvoSuite | Test generator | Bytecode | Tests | Not verified | **Absent.** `TOOLING.md` already recommends |

**Dependency representation:** class-level `jdeps` plus ArchUnit, as now. It agreed with ArchUnit on
97%, 91%, 93% of package edges [R]. In this audit regex recovered 66% of bytecode edges [M], so no regex
may feed a graph. `dsarp/source_index` still is regex-based; `TECHNICAL_REPORT.md` describes it as the
fallback graph. Keep it out of planning.

**Detector mismatch to resolve.** Supplied Log4j2 CSV: 363 package cycles [M]. Arcan 1.2.1 under
DSARP-OpenRewrite: 223 [R]. Under this repo: 535 summed by module, 599 merged, and 5 true SCCs [R].
Same commit-family, four numbers. Every report must state which.

**Unexplained:** merged Arcan reports 104 "strictly cross-module" findings, including an `spi` ↔
`core.context.internal` cycle. Maven forbids module cycles, so this needs explaining before anyone
relies on it. Split packages or test-support modules are plausible; unverified.

---

## 12. Deliverable 10: smell-to-repair matrix

| Smell | Cause analysis | Strategy, in order | Evidence |
|---|---|---|---|
| Cyclic, small SCC | Tarjan, then edge carriers | Move sets dissolving the SCC; merge package as an option when safe | Predicted [M] |
| Cyclic, giant SCC | Same | Named edges only. Do not claim cycles | 18/18 edges [R] |
| Cyclic, class-level inside a package | Class SCC | Inversion. Move cannot help | commons-codec [R] |
| Unstable | Stable-to-unstable edges | Inversion, Move Class | Not bytecode-verified |
| Hub-like, God Component | Fan, cohesion | **Do not split.** Report only | 77/78 predicted worse [R] |
| Scattered | Concern grouping | Merge package | Not measured |
| Design smells | Designite | Stock catalogue | 7 of 2,085 validated [R] |
| Hierarchy | | Refused | |

### Operator catalog

| Operator | Prerequisites | Graph effect | API risk | Automation | Status |
|---|---|---|---|---|---|
| Move Class | Access, same module, no name-ordered dispatch | Relabel node | High if public | High | **Works** |
| Move class set | Same, jointly | Relabel set | High | High | `package_edges_after` supports groups; planner does not |
| Invert edge | Instance methods, declarations, no `new` | Replace with abstraction | Low | Low: 1 of 18 | Keep where unblocked |
| Service locator | Single construction site | Removes construction edge | Low | Medium | **New, Shah** |
| Inline constant | Compile-time constant | Removes edge; bytecode already inlines | Low | High | **New.** May explain some source-only edges |
| Extract to package | Placement acyclic | New node | Medium | Low: 0 of 4 | Fix placement and cost first |
| Merge Package | No collision, no subpackages | Removes node | High | High | Exists |
| Move Method | | | | | **Do not build yet:** 0 of 5 edges removed in SWE-Refactor check [R] |
| Split Package | | Worsens graph | | | **Closed** |

**Two doc fixes.** `CHEAP-EDGE ELIMINATION IS DEAD` refers to **inversion** on cheap edges (0 of 18
legal), while **moves** on single-carrier edges worked 18 of 18, so the heading misleads. And
`negative-results.md` plus the 2026-10-02 status say "within one on 18"; the 2026-09-23 data and the viva
bank say within two.

---

## 13. Deliverable 11: transformation-engine matrix

Settled by the project [R]; this summarizes.

| | OpenRewrite | Spoon | Eclipse JDT/LTK | JavaParser | jdtls | LLM patch |
|---|---|---|---|---|---|---|
| Coverage | `ChangeType`, custom recipes | Custom | Broad, preconditions | Custom | Exposed actions | Any |
| Semantics | Typed LST | Typed AST, `noClasspath` tolerant | Strongest | Needs SymbolSolver | Strong | None |
| Formatting | Strong | Sniper unusable for moves [R] | Strong | Lexical preserve | Strong | Variable |
| Headless | Maven plugin, forks lifecycle | Yes | Needs OSGi workspace [R] | Yes | Protocol work | Yes |
| License | Core Apache-2.0; some recipes Moderne [P] | MIT or CeCILL-C [P] | EPL [U] | Not verified | Not verified | Provider |
| Status | Agrees with Spoon 11 of 12 [R] | Primary | Deferred | Skip | Skip | Gated arm only |

**Choice:** Spoon for planning runs. OpenRewrite for reviewable patches and migration recipes.
JDT only if inversion becomes a priority. Pin `rewrite-maven-plugin` 6.46.1 or later; 5.42.1 half-applies.
Note DSARP-OpenRewrite pins 6.12.0; unverified whether it has the same defect.

### Executor contract

```python
class Executor(Protocol):
    def can_execute(self, candidate: Candidate) -> Applicability: ...
    def plan(self, candidate: Candidate) -> Plan: ...
    def dry_run(self, plan: Plan, work_copy: Path) -> Patch: ...
    def apply(self, plan: Plan, work_copy: Path) -> Patch: ...
    # rollback = discard the copy
```

---

## 14. Deliverable 12: pipeline

```text
repo@commit -> compile (same module set enforced)
  -> Arcan merged root + Designite, raw kept
  -> ArchUnit + jdeps -> Tarjan
  -> target selection: SCC size ascending, then named edge
  -> beam over move_effect, access precheck, public-API flag
  -> Spoon in copy -> residual check -> compile with tests
  -> comparable -> edge_verdict -> japicmp -> tests vs baseline
  -> level assignment -> regression rule -> append-only ledger
```

Roles: detector is oracle; graph explains; planner proposes; engine edits; compiler and tests check
behavior; same detector verifies; an LLM may propose and never certifies.

---

## 15. Deliverable 13: schemas

`docs/schemas/` already holds suggestion and review schemas. Three additions:

```json
{"smell": {
  "project": "", "commit": "", "detector": "arcan", "detector_version": "1.2.1",
  "detector_mode": "merged-root", "detector_sha256": "",
  "smell_id": "sha1(type|granularity|sorted members)",
  "smell_type": "cyclic_dependency", "granularity": "package",
  "affected_components": [], "causal_edges": [
    {"from": "a", "to": "b", "carriers": ["a.C -> b.D"], "kinds": ["Method calls method"]}],
  "scc": {"id": "", "size": 0}, "severity": null, "technical_debt": null,
  "metrics": {}, "raw_evidence": {"file": "", "row": 0, "sha256": ""}
}}
```

```json
{"candidate": {
  "candidate_id": "", "target": {"kind": "scc | edge", "id": ""},
  "operations": [{"op": "moveClass", "type": "", "toPackage": ""}],
  "origin": "deterministic | search | llm",
  "predicted": {"removed": [], "added": [], "participation_delta": 0, "scc_left": 0},
  "success_criterion": "stated before the run",
  "risk": {"public_api": true, "name_ordered_dispatch": false, "text_references": []},
  "compatibility_plan": "none | facade | migration_recipe"
}}
```

```json
{"execution": {
  "candidate_id": "", "base_commit": "", "patch_sha256": "", "files_changed": 0,
  "gates": {"before_apply": {}, "after_apply": {}, "comparable": {}, "structural": {},
            "api": {"tool": "japicmp", "binary_breaks": []}, "behavioural": {}},
  "measured": {"removed": [], "added": [], "scc_left": 0},
  "prediction_error": {"added": 0, "removed": 0},
  "level": "4b", "decision": "accepted | rejected", "failed_gate": null, "why": null
}}
```

---

## 16. Deliverable 14: candidate ranking

Hard filters first: access, same module, predicted removal, no new SCC member, facade direction.

```text
score = 4·dissolved + 2·Δparticipation + 1·Δscc_edges
        − 0.5·moves − 2·public_api_without_plan − 1·text_references
```

Each Δ is positive when better. Weights are judgment, frozen before any fresh repository, with a
sensitivity check. This is **a calculation, not a fitted model**, so it does not repeat the five
failures in `negative-results.md`. Severity plays no part: ATDI ordering is anti-predictive [R].

**Search decision.** Greedy within one SCC first, then beam width 5, depth 4. In this audit greedy
needed 1 to 7 moves on SCCs up to 15. Beam fits since `move_effect` takes seconds. NSGA-III adds Pareto
spread that a single-gate acceptance loop cannot use, so keep it out. A* lacks a useful heuristic.

Measured on Log4j2, 17 modules, main code only [M]:

| SCC | Result |
|---|---|
| 2 packages, `layout.template.json` | **One move dissolves it**: `JsonTemplateLayout -> resolver`, no new package in any cycle |
| 2 packages, `log4j.io` | No single move helps; 7 and 10 class edges |
| 10 packages, `log4j` API | Greedy 4 moves: 10 to 6 |
| 15 packages, `log4j` 1.2 bridge | Greedy 7 moves: 15 to 8 |
| 36 packages, core | 76 to 52 reciprocal pairs in 12 moves; size 36 to 35 |

Other figures: 37 of 76 reciprocal pairs have one class edge in the lighter direction, 63 have at most
5. 2,375 same-module moves were considered; 111 (4.7%) strictly improve. 49 of 76 pairs are removable
by one move, 42 without creating a new pair.

**Limits.** Moved class keeps all edges. No access, API, or test modeling. Scope differs from the
project's snapshot (36 vs 50 for the largest SCC, since test modules are excluded). `JsonTemplateLayout`
is a public plugin class, so its move needs a compatibility decision. The first greedy runs sampled 500
moves per step on the core SCC only.

---

## 17. Deliverable 16: roadmap

Everything lands on the `infallible` branch line.

| Phase | Files | Done when |
|---|---|---|
| 0 Consolidate | Merge `clever-bassi` and `agent-workflow` deltas; reconcile Spoon; push | One branch holds all work |
| 1 Instrument | `tools/arcan_runner.py` merged default, explain cross-module; new `tools/api_runner.py` (japicmp); `verification/gates.py` records `api` as advisory; new `experiments/placebo.py` | Placebo delta is zero, or the reason is known |
| 2 Small-SCC experiment | `refactoring/scc_planner.py` over `package_edges_after`; `experiments/scc_dissolve.py` | Pre-registered run on log4j2, pdfbox, tika, 5-10 SCCs each |
| 3 Regression rules | `tools/archunit_runner.py` emit rule per accepted change | Rule fails on reverted patch |
| 4 Behavior | EvoSuite on touched types | Tika ServiceLoader-type case caught without its test |
| 5 Operators | Service locator, constant inline; composite placement check | Inversion reach above 18% of edges |
| 6 LLM veto | `agents/move_veto.py`, enumerate-and-pick, pre-registered | Arm E vs C reported either way |
| 7 Generalize | Karaf, Struts, smaller Apache, Gradle | Protocol on 5+ systems |

Fix in DSARP-OpenRewrite only if it stays in use: real tool hash in `summarize()`, per-candidate claim,
remove `-DskipTests`, drop `is_public` from sort, strip comments before `TYPE_RE`.

---

## 18. Deliverable 17: experimental protocol

Systems: log4j2, pdfbox, tika (baselines exist), then commons-validator, Struts, Karaf.

For each: pin commit; prove baseline build and tests with `-fae`; detect twice; run arms; log all
candidates; inspect a stratified sample of 20 accepted patches or all, two raters where possible.

Primary metrics: prediction error; SCC dissolution rate by size; concretization rate; transformation
success rate; behavioral validation rate; architectural success rate by level; end-to-end rate; API
survival rate. Report placebo beside every delta.

Statistics: funnels with Wilson intervals; McNemar on paired targets; effect sizes; no significance
claims from n = 3 systems. **Pre-register selection before running**, as the project already learned.

False positives: sample Arcan cycles against ArchUnit SCCs. SmellBench found 63.1% with its detector [P].

---

## 19. Deliverable 18: ablation

Arms B and C exist already under project naming. Mapped to the brief:

| Arm | Planner | Graph | Sim | Status |
|---|---|---|---|---|
| A | Transformer + generator | Regex | No | Done: 0 of 120 |
| B | Deterministic rules, unfiltered | Bytecode | No | Run |
| C | Rules + `move_effect` | Bytecode | Yes | Done, 3 repos |
| D | SCC beam | Bytecode | Yes | Run |
| E | D + LLM veto | Bytecode | Yes | Run |
| F | LLM planner | Source | No | Run, Pandini two-step |
| G | D + E + Shah operators | Mixed | Yes | Run |
| H | Abdeen annealing, plus Shah if available | Own | Own | Run |
| P | **Placebo**: neutral edit | | | **Run first** |

Same targets, attempt budget, gates, oracle. The known confound stays visible: arms receive different
information, so a win shows information helps, not that a method dominates.

---

## 20. Deliverable 19: risks

| Risk | Mitigation |
|---|---|
| False-positive smells | Compare Arcan cycles with ArchUnit SCCs; sample |
| Tool disagreement | Report it. Four cycle counts exist for Log4j2 already |
| Parser failures | Bytecode graph; Spoon `noClasspath`; rejection reasons |
| Reflection, plugins, SPI | `name_references`, string literal rewrite; tests; Log4j2 `@Plugin` is high risk |
| Name-ordered dispatch | Add a precheck for `ServiceLoader` or sort-by-class-name use, from the Tika case |
| Generated source, annotation processing | Full rebuild; `comparable` gate |
| Multi-module | Same-module moves; explain cross-module findings first |
| Gradle | Test verdict exists [R]; runner parity unverified |
| JPMS, OSGi | Update exports; Log4j2 bnd baseline |
| Public API | japicmp, facade rule, migration recipe |
| Flaky tests | Triple baseline, by test ID |
| Environment | Container; JDK pin (JDK 26 caused red baselines [R]) |
| Runtime | Prediction first; tests only on survivors |
| Licensing | Arcan terms unverified; Designite must not be redistributed |
| Reproducibility | Hashes, append-only ledger; **push the branch** |
| Behavior preservation | Tests are a floor; EvoSuite; report coverage of touched classes |
| Construct validity | A move can game a metric without better design; HGRS on accepted patches |
| Small-SCC bias | Small SCCs may be low value. Report value honestly; do not generalize to tangled cores |
| Overfitted weights | Freeze before fresh repos |
| Stale docs | `TECHNICAL_REPORT.md`, README and interim artifact disagree with current results |

---

## 21. Deliverable 20: final ranked recommendation

1. **Bytecode planning with SCC targeting and full gates.** Moderate to high. Extends what already
   works; answers the one claim the project has never reached.
2. **Same, with beam search and Shah operators.** Moderate. Needed once single-move dissolves run out.
3. **Graph plus LLM veto.** Moderate as a quality filter. Fixes structural moves that are bad designs.
4. **LLM patch writing behind gates.** Low to moderate. Only for outside-template repairs.
5. **Multi-agent planner.** Low to moderate. Cost unjustified until 3 and 4 show value.
6. **Pure LLM agent.** Low.
7. **Transformer classifier.** Very low. Keep as arm A.

### The twelve decisions

1. **First smell:** Cyclic Dependency, package level, smallest SCCs first.
2. **Detector:** Arcan 1.2.1 merged-root, with ArchUnit and jdeps as verifying oracles. Designite kept separate.
3. **Representation:** class-level bytecode graph.
4. **Candidates:** in-SCC single-carrier moves and move sets from `package_edges_after`.
5. **Search:** greedy per SCC, then beam 5 by 4.
6. **Engine:** Spoon for runs; OpenRewrite for patches and downstream recipes.
7. **LLM:** yes, narrowly, later.
8. **Where:** veto or pick among valid plans. Never in gates.
9. **Reuse:** `f82d2ca` entire; Abdeen objective; Shah operators; SmellBench reporting; Pandini prompts for arm F.
10. **Avoid:** classifier work, package splitting, a sixth smell-delta ranker, Move Method without a
    purpose, NSGA-III, smell-count headlines, regex graphs, batched attribution.
11. **MVP:** one pre-registered result: of K small SCCs on three systems, how many dissolved, with tests,
    API status, and placebo beside it. Even a low number is publishable.
12. **Future work:** giant SCC restructuring, Hub and God Component policy, composite extraction, CI bot.

### Open decisions

- **Public API:** decided 2026-11-01. Moves of public classes count as success, and each binary break
  is reported with the result. Headlines state both the all-moves rate and the API-compatible rate.
- **Success definition:** decided 2026-11-01. The Level 4a/4b/4c amendment replaces the brief's wording.
- **Arcan version:** which version produced `baseline_csv`, and are its terms OK for publication?

---

## 22. Bibliography

**Peer-reviewed**

- Pandini et al., 2025. https://ieeexplore.ieee.org/document/11015021/
- Kuo et al., 2024. https://doi.org/10.4018/IJSI.339884
- Nursapa et al., 2025. https://arxiv.org/abs/2507.12561
- Abdeen et al., 2009. https://doi.org/10.1109/wcre.2009.13
- Mkaouer et al., 2015. https://dl.acm.org/doi/10.1145/2729974
- Ouni et al., 2016. https://dl.acm.org/doi/abs/10.1145/2932631
- Lin et al., 2016. https://doi.org/10.1145/2950290.2950317
- Mitchell, Mancoridis, 2008. https://researchdiscovery.drexel.edu/esploro/outputs/journalArticle/On-the-evaluation-of-the-Bunch/991019167811504721
- Terra et al., 2013. https://www.llp.dcc.ufmg.br/Publications/Journal2013/2013-spe-terra-reparing.pdf
- Oyetoyan et al., 2015. https://www.researchgate.net/publication/282504460_A_Decision_Support_System_to_Refactor_Class_Cycles
- Sas et al., 2019. https://research.rug.nl/en/publications/investigating-instability-architectural-smells-evolution-an-explo/
- Arcelli Fontana et al., 2017. https://boa.unimib.it/handle/10281/155470
- Search-based refactoring survey. https://link.springer.com/article/10.1186/s40411-018-0046-4
- Shah thesis, 2013. https://mro.massey.ac.nz/handle/10179/5176

**Preprints and artifacts**

- SmellBench. https://arxiv.org/abs/2605.07001
- Pandini, Goknil. https://zenodo.org/records/19819717 and https://zenodo.org/records/14745953
- MANTRA. https://arxiv.org/abs/2503.14340
- RefAgent. https://arxiv.org/abs/2511.03153
- Agentic Refactoring. https://arxiv.org/abs/2511.04824
- Two-class cycle patterns. https://arxiv.org/abs/2306.10599
- DCLfix. https://arxiv.org/abs/1506.07589
- Ripple. https://arxiv.org/abs/2610.24790
- ArchGuard-APR. https://arxiv.org/abs/2610.33853

**Tool documentation**

- Arcan wiki. https://essere.disco.unimib.it/wiki/arcan/
- DesigniteJava. https://github.com/tushartushar/DesigniteJava
- OpenRewrite licensing. https://docs.openrewrite.org/licensing/openrewrite-licensing
- Spoon. https://github.com/INRIA/spoon
- ArchUnit. https://www.archunit.org/userguide/html/000_Index.html
- jQAssistant. https://jqassistant.github.io/jqassistant/current/
- CK. https://github.com/mauricioaniche/ck
- japicmp. https://github.com/siom79/japicmp
- Revapi. https://github.com/revapi/revapi

**Industrial tooling**

- Arcan Tech. https://www.arcan.tech/
- Sonargraph. https://www.hello2morrow.com/products/sonargraph
- Sonargraph cycle analysis. https://blog.hello2morrow.com/2015/02/identifying-dependencies-for-cycle-removal/
- Sonar acquires Structure101. https://www.sonarsource.com/de/company/press-releases/sonar-acquires-structure101-to-strengthen-code-quality-offering/
- SonarQube Architecture. https://docs.sonarsource.com/sonarqube-server/architecture

**Project documents, branch `f82d2ca`**

`docs/negative-results.md`, `docs/suggestion-ledger.md`, `docs/coverage.md`, `docs/batch-detail.md`,
`docs/viva-question-bank.md`, `docs/smell-refactoring/{TOOLING,COUNTERMEASURES,METHODS,PROGRESS}.md`,
`data/memory/current_status.md`, `dsarp/refactoring/move_planner.py`, `dsarp/verification/gates.py`.

**Reproducing the measurements**

Clone both repos, check out the pinned Log4j2 commit, compile on JDK 17:

```bash
./mvnw -DskipTests -pl log4j-api,log4j-core,log4j-1.2-api,log4j-layout-template-json,log4j-jul,log4j-iostreams,log4j-web,log4j-jdbc-dbcp2,log4j-jpa,log4j-mongodb,log4j-slf4j2-impl,log4j-to-slf4j,log4j-spring-boot -am compile
```

Then run `baseline_and_regex.py <root>`, `simulate2.py <root> <jdeps>`, and `simulate3.py <root> <jdeps>`
from `research/log4j2_feasibility/`, where `<root>` holds `dsarp-or/`, `l4j/`, `analysis/`. Run
`baseline_and_regex.py` first, since `simulate2.py` reads the manifest it writes to `analysis/gen/`.
`simulate.py` is the first version, kept because its per-pair figure was wrong (`86 of 76`) and
`simulate2.py` replaced it. The generator run forces `Move Class` on all 717 rows, matching documented collapse. Its
237 candidates differ from 40 in `docs/VALIDATION.md` because `36b6e97` removed the candidate limit.
