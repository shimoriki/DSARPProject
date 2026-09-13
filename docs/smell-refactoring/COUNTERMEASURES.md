# Countermeasures: what the literature says about the problems this system hit

Written 2026-09-12, after a full experiment across pdfbox, tika, log4j2 and commons-validator.

Every issue below is one this system actually hit and diagnosed, not a hypothetical. For each,
this records what the published work does about it, and whether that changes what we should do.

The short version: **almost every problem we found is a known, named problem with published
countermeasures, and several of our accidental design choices are the ones the literature
recommends.** The two places we are genuinely behind are the operation set and the fitness
function.

---

## 1. Our numbers, against published precedent

This is the comparison that was missing. Our measurement is "apply one move, does the smell
count fall", which is stricter than most published evaluations (those usually measure
agreement with a developer's historical choice, not effect on a metric).

| system | what it measures | reported |
|---|---|---|
| **DSARP (this system)** | applied move reduces the targeted smell, tests no worse | **32%** (pdfbox, n=25) |
| **DSARP, net** | ...and total smells also fall | **24%** |
| JMove | agreement with a known-good move method | precision 21–32%, recall 21–60% |
| JDeodorant | same | precision 5–15%, recall 35–40% |
| ROSE (CodeBERT/CodeT5) | classify which method suits a smell | 96.9% accuracy, 95.2% F1 |
| ChatGPT, unconstrained | identify a refactoring opportunity | 28 of 180 = 15.6% |
| ChatGPT, search space narrowed in prompt | same | **86.7%** |
| Bavota et al. | code smells removed by *intentional* developer refactoring | **7%** |
| Guice study | cyclic-dependency smells removed in the class where detected | **8–11%** |

Two things fall out of this table.

**Our 32% is not bad; it is in the same band as the best dedicated move-recommendation tools**,
and it is measured on a harder question. JMove's 21–32% precision is agreement with a
developer; ours is a measured effect on a detector. ROSE's 96.9% is a different task
altogether — classifying which *method* applies, never applying it — which is exactly why
this project stopped trusting it.

**Human developers remove architectural smells at 7–11%.** A tool that lands a measured
reduction on a third of its attempts is not obviously worse than the humans whose behaviour
the training data encodes. This reframes the ">50%" goal: 50% may be above what the
*practice* achieves, not merely above what our system achieves.

---

## 2. Issue by issue

### 2.1 Preconditions that miss accessibility (our test-source precheck gap)

**What we hit.** `precheckInRoot` modelled only `src/main/java`. commons-validator's
`ISBNValidator` moved `routines -> routines.checkdigit`, main compiled, Arcan measured 21
smells, and then `testCompile` died on `ISBN10_REGEX is not public`. The precheck had called
it legal.

**What the literature says.** This is a named defect class: *overly weak preconditions* —
"implemented preconditions are insufficient to guarantee behavior preservation or syntactic
correctness, which may introduce compilation errors". It is not an exotic failure:

- 34 overly weak preconditions were identified in **Eclipse**;
- Eclipse, NetBeans and IntelliJ have all been shown to have **flaws preserving accessibility**
  during refactoring, with Pull Up Members changing behaviour;
- the root cause given is that "specifying preconditions is a non-trivial task, developers may
  be unaware of the preconditions needed".

**Verdict.** Our bug is the same defect that mature commercial refactoring engines ship. The
fix we applied (model test sources too, report `testsModelled` when we cannot) is the right
shape. The literature's stronger answer is *differential testing of the engine itself* —
generating programs and checking the engine's own preconditions — which is a bigger
investment than this project needs today.

**Action: done, no further work needed.** Keep `testsModelled` in the output; a legality
verdict that silently weakened itself is worse than one that admits it.

### 2.2 "It compiles" is not behaviour preservation (our Tika ServiceLoader finding)

**What we hit.** Moving `FileCommandDetector` from `tika.detect` to `tika.utils` compiled
cleanly and broke `ServiceLoaderUtilsTest.testSort`, because Tika sorts service
implementations by fully-qualified class name — the move changed detection priority.

**What the literature says.** Exactly our conclusion, stated directly: "Behavior preservation
is typically verified by compiling the refactored program and executing its test suite.
However, this strategy may fail to capture more subtle behavioral deviations, and many
developers' test suites are insufficient."

The named countermeasure is **SAFEREFACTOR**: compile, then generate a test suite with
Randoop *for the methods affected by the change*, and run it before and after. It does not
rely on the project's own tests being adequate.

Recent LLM work quantifies the same risk: of 8,096 LLM-refactored segments, **928 showed
behavioural inconsistencies**; 13 of 176 ChatGPT solutions "changed the functionality or
introduced syntax errors".

**Verdict.** Our test stage is the right instinct and is doing real work — it is what caught
the ServiceLoader reorder. But project tests are a floor, not a guarantee.

**Action worth taking:** generate tests for affected types rather than only running the
project's suite. This is the single highest-value addition on this list, because it attacks
the exact failure the Tika case demonstrated.

### 2.3 Test baselines that are already red (our log4j2 false 0%)

**What we hit.** log4j2 reported `label_strict 0/22` — every smell-reducing move appeared to
break tests. All four reported identical `6 failures / 29 errors`, all four were in
`log4j-1.2-api`, and every failing test was in `log4j-api` (`testSerializable`, `LogManagerTest`)
on a JDK 26 toolchain. The suite was already red; we had never measured the baseline.

**What the literature says.** This is the flaky/pre-existing-failure problem that regression
testing research addresses by *differencing* rather than thresholding, and it is why
SAFEREFACTOR runs its suite **before and after** rather than only after.

**Verdict.** Our design assumed a green baseline and never checked it — a pure measurement
bug, and the most dangerous kind, because "0%" looks like a finding.

**Action: done.** `tests_no_worse_than_baseline` replaces "tests pass"; baseline is measured
once per repo and stored.

### 2.4 Optimising one metric while damaging others (our targeted vs collateral split)

**What we hit.** `PDResources` reduced its targeted smell by 2 and added 3 elsewhere —
scored as a success while the repository got worse. `PDTransparencyGroupAttributes` did the
reverse: targeted 0, collateral −11, scored as a failure while the repository got better.
The "reduced" set and the "improved" set are different sets, neither containing the other.

**What the literature says.** This is the entire motivation for **multi-objective
search-based refactoring**. MORE (NSGA-III) optimises design quality, smell correction and
design-pattern introduction simultaneously; Ouni et al. use NSGA-II over quality and effort;
robustness variants add "do not introduce new defects" explicitly as an objective, and return
a Pareto front rather than a single answer.

**Verdict.** Single-objective targeted-delta is known to be inadequate, and we rediscovered
why. We now report three measures (`label`, `label_strict`, `label_net`); `label_net` is
closest to a scalarised multi-objective score.

**Action worth taking:** rank candidates by *expected total smell reduction*, not by whether
the targeted smell falls. Our own data argues for this: `MissingOperandException` alone was
−240 of −289 total.

### 2.5 Ranking by severity does not find fixable problems (our ATDI result)

**What we hit.** Sorting candidates by ATDI and trialling them in order, the higher-ATDI half
produced 2/12 wins and a summed **+12** smells; the lower-ATDI half produced 6/13 wins and
**−273**. The severity score points away from the fixable moves.

**What the literature says.** There is direct support for separating these concerns: "A robust
multi-objective approach to **balance severity and importance** of refactoring opportunities"
exists precisely because severity alone is the wrong ranking. And the industry-disconnect work
("Mind the Gap") reports that the criteria recommendation tools rank by are not the criteria
practitioners use.

**Verdict.** Ranking by detector severity is a known mistake and we have now measured it in
our own data. Every batched run this session drew candidates from the top of that ranking,
which is a substantial part of why they all came back positive-delta.

**Action worth taking:** rank by predicted *effect*, learned from outcome labels — which is
what the labelling run is for.

### 2.6 Our operation set is too narrow (moveClass only)

**What we hit.** 7 of 8 pdfbox improvements targeted Cyclic Dependency, but so did most of the
failures — targeting a cycle is necessary, nowhere near sufficient. God Component, Hub-Like
and Unstable Dependency essentially never yield to moving one class.

**What the literature says.** The canonical cycle-breaking techniques are: **introduce an
interface to invert the dependency (DIP)**, move methods/fields to the right abstraction,
merge tightly-coupled modules, and extract classes or split subsystems. Dependency Inversion
is the *primary* named technique; moving a class is one of several and not the main one.

**Verdict.** This is our biggest genuine capability gap. We implement exactly one of the four
standard techniques, and not the one the literature leads with. It also explains why God
Component barely responds: that smell is a property of a package's size and cohesion, and
relocating a single class does not change it meaningfully.

**Action worth taking (largest expected gain):** implement Extract Interface + Dependency
Inversion as a second operation. The project already has a custom OpenRewrite recipe stub for
extract-interface and RefactoringMiner data for it (though only 6 real mined instances).

### 2.7 Evaluations that cannot be compared (our 50% -> 32% -> 24%)

**What we hit.** The same system reported 50%, then 32%, then 24%, depending on sampling
(head vs stride), metric (targeted vs net) and whether tests were checked.

**What the literature says.** "Different authors have different evaluations of Move Method
refactoring algorithms, which leads to results reported by different papers that do not
correlate with each other and it is almost impossible to understand which algorithm works
better in practice." The proposed countermeasure is a shared synthetic benchmark with
injected smells.

**Verdict.** Our instability is the field's instability. The lesson is to state the sampling,
the metric and the baseline with every number — and never to quote a rate without them.

**Action: done by convention.** All three measures are reported together from now on.

### 2.8 Small mined datasets (our thin methods)

**What we hit.** RefactoringMiner yields very few instances for some methods — Extract
Interface 6, Split Package 1 — far from the 50-per-method target.

**What the literature says.** The standard countermeasure is **synthetic dataset generation by
injecting smells**: take clean code, move a method/class to where it does not belong, and you
have a labelled instance with known ground truth. This is explicitly proposed for "generating
large synthetic datasets suitable for both algorithms evaluation and building complex machine
learning models".

**Verdict.** Viable and cheap for us, since our pipeline can already apply a move
mechanically — running it *backwards* manufactures training instances.

**Caveat:** synthetic instances test recovery of an injected fault, which is an easier problem
than finding a real one. It should supplement mined data, not replace it.

---

## 3. Where our design is already the recommended one

Worth recording, because these were arrived at by failure rather than by reading:

**Enumerate-and-pick beats free generation.** We stopped letting the model write Spoon edits
and made it choose among pre-validated candidates by index, after repeated malformed output.
The LLM refactoring study measures exactly this effect: ChatGPT identified 15.6% of
opportunities unconstrained, and **86.7% when the prompt narrowed the search space**. Our
architecture is the published best practice.

**Validate by applying, not by asking.** ROSE reports 96.9% accuracy on classifying which
method suits a smell and never applies anything. Our whole pipeline exists because that number
does not predict whether the smell goes away. The literature agrees the useful question is
behaviour preservation plus measured quality change.

**Per-candidate attribution over batches.** Our batched runs reported a net figure that hid
four good moves behind one bad one. Isolating each change is what makes any of the outcome
data usable.

**Keeping the logs.** Two OpenRewrite failures were unexplained for a whole run because the
work directory was deleted. "It did not compile" is not a diagnosis; the javac line is.

---

## 4. Recommended next actions, in order of expected value

1. **Extract Interface / Dependency Inversion as a second operation.** The canonical
   cycle-breaking technique, and we do not have it. Largest expected gain (§2.6).
2. **Rank by predicted total smell reduction, not detector severity.** Our own data shows
   severity ranking is anti-predictive, and value is extremely concentrated (§2.4, §2.5).
3. **Generate tests for affected types (SAFEREFACTOR-style)** instead of relying only on the
   project suite. Directly attacks the Tika ServiceLoader failure mode (§2.2).
4. **Synthetic smell injection** to fill the thin methods, clearly labelled as synthetic and
   reported separately from mined data (§2.8).
5. Leave the precheck and baseline-test work where it is — both are done and both match what
   the literature recommends.

---

## Sources

- [ROSE: Transformer-Based Refactoring Recommendation for Architectural Smells](https://arxiv.org/pdf/2507.12561)
- [JMove: A novel heuristic and tool to detect move method refactoring opportunities](https://www.sciencedirect.com/science/article/abs/pii/S0164121217302960)
- [Ten Years of JDeodorant: Lessons Learned from the Hunt for Smells](https://users.encs.concordia.ca/~nikolaos/publications/SANER_MIP_2018.pdf)
- [Evaluation of Move Method Refactorings Recommendation Algorithms: Are We Doing It Right?](https://ieeexplore.ieee.org/document/8844425/)
- [Detecting Overly Strong Preconditions in Refactoring Engines](https://pauloborba.cin.ufpe.br/publication/2018detecting_overly_strong_preconditions_in_refactoring_engines/2018TSEStrongPreConditionsRefactoringEngines.pdf)
- [Towards Understanding Refactoring Engine Bugs](https://doi.org/10.1145/3747289)
- [Automated Behavioral Testing of Refactoring Engines (SAFEREFACTOR)](https://www.microsoft.com/en-us/research/wp-content/uploads/2020/08/tse12.pdf)
- [On Preserving the Behavior in Software Refactoring: A Systematic Mapping Study](https://arxiv.org/pdf/2106.13900)
- [MORE: A multi-objective refactoring recommendation approach](https://onlinelibrary.wiley.com/doi/abs/10.1002/smr.1843)
- [A robust multi-objective approach to balance severity and importance of refactoring opportunities](https://link.springer.com/article/10.1007/s10664-016-9426-8)
- [An Empirical Study on the Potential of LLMs in Automated Software Refactoring](https://arxiv.org/abs/2411.04444)
- [An empirical study of LLM-based refactoring consistency](https://link.springer.com/article/10.1007/s10664-026-10911-6)
- [On the evolution and impact of Architectural Smells - an industrial case study](https://arxiv.org/pdf/2203.08702)
- [An empirical investigation of the impact of architectural smells on software maintainability](https://www.sciencedirect.com/science/article/pii/S0164121225000500)
- [Mind the Gap: The Disconnect Between Refactoring Criteria Used in Industry and Refactoring Recommendation Tools](https://www.researchgate.net/publication/387239150_Mind_the_Gap_The_Disconnect_Between_Refactoring_Criteria_Used_in_Industry_and_Refactoring_Recommendation_Tools)
- [DCL60-J. Avoid cyclic dependencies between packages (SEI CERT)](https://wiki.sei.cmu.edu/confluence/display/java/DCL60-J.+Avoid+cyclic+dependencies+between+packages)
