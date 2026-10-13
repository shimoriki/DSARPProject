# DSARP — examiner question bank

Written as the examiner, not as the student. Every answer below is grounded in a figure this
project actually measured; where the honest answer is "we do not know", it says so, because an
examiner can smell a fabricated defence from across the room.

Quick index:

1. [Two landmines in the current deck](#1-two-landmines-in-the-current-deck)
2. [Definitional recall — do you know your own terms](#2-definitional-recall)
3. [Measurement validity — the hardest attacks](#3-measurement-validity)
4. [The model](#4-the-model)
5. [Causality and inference](#5-causality-and-inference)
6. [Construct validity — is smell count even the right target](#6-construct-validity)
7. [Defending a negative result](#7-defending-a-negative-result)
8. [Engineering specifics](#8-engineering-specifics)
9. [Questions you should want to be asked](#9-questions-you-should-want-to-be-asked)
10. [Three answers to never give](#10-three-answers-to-never-give)

---

## 1. Two landmines in the current deck

### Q. "You say 18 of 18 planned moves worked. Did the tests pass?"

**Why it is dangerous.** The slide says "applied, compiled, and removed the exact dependency edge
they were aimed at". It does not say accepted. The honest number is **14 of 18**.

**The answer.** All 18 applied, built and removed their target edge. Four were then rejected *by
the test suite*, not by the structure. Three of the four are Tika: `ParseContext` twice and
`StringUtils`, producing 24 failures and 17 errors against a baseline of 1 failure and 3 errors.
`ParseContext -> metadata` was structurally the strongest candidate the project has produced — 71
edges removed, 7 added, with jdeps independently agreeing — and it breaks 37 tests. Under a
smell-count-only validator it would have been recorded as a large win. That is precisely the
failure mode the test gate exists to catch, so we report it as a rejection rather than a victory.

### Q. "Your planner predicts move cost within one edge?"

**The answer.** Within **two**, on 18 of 18. Exact on 14 of 18. (For edges *removed*, exact on
7 of 12, within two on 12 of 12, recorded only from the log4j2 run onward.) If your slide says
"within one", correct it before you present.

---

## 2. Definitional recall

Examiners open with these to find out whether you understand your instruments or merely ran them.

### Q. "Define a cyclic dependency. Precisely."

A set of components — packages or classes — where a directed dependency path exists from each
member back to itself. Formally a strongly connected component of size ≥ 2 in the dependency
graph. Arcan reports them as a membership matrix: one row per cycle, one column per component,
`1` where that component is a member.

**The follow-up that catches people:** *"So if you remove one edge in a cycle, is the cycle
gone?"* **No.** A strongly connected component survives until every return path is cut. This is
the single most important structural fact in the project — see §3.

### Q. "What is an unstable dependency?"

A violation of Martin's Stable Dependencies Principle. Instability is

    I = Ce / (Ca + Ce)

where `Ca` is afferent coupling (incoming dependencies — who depends on me) and `Ce` is efferent
coupling (outgoing — who I depend on). `I = 0` is maximally stable, `I = 1` maximally unstable.
The principle says depend in the direction of *increasing* stability; a package should not depend
on one that is less stable than itself.

**Worked example from our own data (commons-validator):**
`org.apache.commons.validator.util` has I = 0.84 and depends on `org.apache.commons.validator`,
which has I = 0.845. The dependency points at something *less* stable, so it is flagged. Arcan
writes these as `(UnstableDependenciesPackage, CorrelatedPackage)` pairs in `UD.csv`.

### Q. "Hub-like dependency?"

A component with both high fan-in and high fan-out — it is depended on by many and depends on
many, so it couples otherwise unrelated parts of the system. Arcan writes `HL.csv` only when it
finds one; commons-validator has none, which is why that file is absent there. Tika's is
`org.apache.tika.utils.XMLReaderUtils`, FanIn 57, FanOut 47.

### Q. "What is the difference between an architectural smell and an implementation smell?"

Architectural smells are properties of the dependency structure between components — cycles, hubs,
unstable dependencies. We detect these with **Arcan**, from **bytecode**. Implementation and
design smells are properties of code within a class or method — long statement, complex
conditional, magic number, feature envy. We detect those with **DesigniteJava**, from **source**.

They are not interchangeable and their counts are not comparable. commons-validator has **18**
architectural smells and **201** implementation smells. Both figures are correct; they count
different things.

### Q. "CBO? LCOM?"

Coupling Between Objects — the number of other classes a class is coupled to. Lack of Cohesion of
Methods — how poorly a class's methods share its fields; higher means less cohesive. Both appear
in Arcan's `CM.csv` and in our `component-metrics.csv`, on CLASS rows only. PACKAGE rows carry
FanIn and FanOut only, because CBO and LCOM are class-level by definition.

### Q. "What are the levels of a C4 model?"

Context, Container, Component, Code. We use the first three. Context is DSARP as one box and what
it talks to; Container is the four runnable concerns (Evidence, Transformation, Validation,
Measurement); Component is the inside of Transformation. We do not present a Code level, because
at that granularity the diagram carries less than the source does.

### Q. "What does OpenRewrite actually operate on?"

A Lossless Semantic Tree — a typed AST that also preserves formatting and whitespace, so a
transformed file round-trips byte-identically except where the recipe changed it. That is why we
use it for source transformation rather than text substitution. We also use **Spoon**, which has
its own AST model; the planned-move experiments in §1 were applied with Spoon.

---

## 3. Measurement validity

This is where a good examiner will spend most of their time, and where the project is strongest.

### Q. "You found a counting bug in your own measurement. How do you know there are no others?"

**Why it is dangerous.** Any answer that sounds like "we are confident there are none" is
a losing answer.

**The answer.** We do not know, and we cannot. What we have instead is a cross-check. The project
measures smell change two independent ways: a **row count** from the detector's CSVs, and an
**identity diff** that matches each smell by what it actually is — a cycle by the set of its
members, an unstable dependency by its package pair, a hub by its class. Those two paths
disagreed on every affected batch. Chasing that disagreement instead of publishing the larger
number is what exposed the bug. After correcting it they agree on **37 of 37** batches.

Two independent measurements agreeing is not proof of correctness. It is, however, a control
that would catch a large class of further errors, and it is the control that caught this one.

### Q. "What exactly was the bug?"

Arcan writes `UD.csv` and `UD30.csv`. `UD30` is the *same* unstable dependencies filtered at a 30%
instability threshold — a severity view, not a second set of findings. Our adapter globbed
`UD*.csv` and read findings from both files, so every severe pair was counted twice. Verified
across 64 Arcan runs: `UD30` is a subset of `UD` in every one, with no pair unique to it.

Corrected baselines: Tika **260 → 252**, log4j2 **767 → 714**, Struts **274 → 227**.

### Q. "Did the correction change your conclusions?"

Magnitudes, yes. Direction, mostly — and this is the part to volunteer rather than conceal.
**Three of 39 comparable verdicts changed direction:**

| batch | as counted | distinct | effect |
|---|---|---|---|
| struts-C4 | −6 | **+8** | reported as a reduction; it is a worsening |
| struts-C1 | −2 | **0** | reported as a reduction; it is neutral |
| log4j2-C3 | +1 | **0** | worsening becomes neutral |

Struts arm C therefore has **one** reducing batch, not three. The best result in the project falls
from −16 to **−6**. Volunteer this. An examiner who discovers you buried a sign flip will discount
everything else you said.

### Q. "Why does the duplicate count not simply cancel in a before/after delta?"

Because the number of duplicated rows varies with the tree — between 6 and 59 across our runs. It
is a function of how many unstable dependencies exceed the 30% threshold at that revision, which
the refactoring changes. A constant offset would cancel; this is not constant.

### Q. "Why do you discard batches? Isn't that cherry-picking?"

The opposite — it is the discipline that prevents cherry-picking. A batch is comparable only if
the refactored tree compiled **the same set of reactor modules** as its baseline. If a module
fails to build, its classes are absent from the bytecode, Arcan cannot see their smells, and the
count drops for a reason that has nothing to do with the refactoring. 19 of 56 batches built a
different module set. Their numbers are real Arcan output, they look like results, and every one
is meaningless. We report that they were discarded and what they would have claimed — the worst
would have read as −92%.

### Q. "Your detector runs on bytecode. Doesn't the compiler change what it sees?"

Yes, and this is a genuine limitation to concede. Arcan reads compiled classes, so anything the
compiler erases or synthesises affects the graph: generics erasure, synthetic bridge methods,
lambda desugaring, inlined constants. We hold this constant by using the same JDK, same Maven
flags and same Arcan jar for every before/after pair, so the *difference* is attributable to the
refactoring. We cannot claim the absolute graph equals the source-level design.

### Q. "Why is a cycle identified by its member set?"

Because a cycle has no stable identifier across two runs — Arcan numbers them `Cycle0, Cycle1…`
in detection order, and those indices shift when anything changes. The member set is the only
property that survives. The consequence is important: two runs can report the *same number* of
cycles with not one cycle in common. Our tika-B7 batch is exactly this — net change zero, ten
smells removed, ten created.

---

## 4. The model

### Q. "Your top-5 hit rate is 0.913. Your macro-F1 is 0.039. Which is the honest number?"

**Macro-F1.** Top-k hit rate rewards a model that always answers with the majority label. Our
training set is 686 rows over 18 labels, and `Move Class` alone accounts for **381** of them —
55%. A classifier that answers "Move Class" to every input scores macro-F1 ≈ 0.040. Ours scores
**0.0387**. It is level with that baseline, which means it has learned the label prior and not a
mapping from smell to fix.

Micro-F1 is 0.353, precision 0.534, recall 0.263 — micro-averaging weights by support and is
therefore also flattered by the majority class. Macro-averaging weights every label equally, which
is what you want when the question is "does it distinguish between refactoring types".

### Q. "Show me the evidence it answers the same thing every time."

Three consecutive Tika prediction records, with 3, 4 and 6 affected elements and different
packages, all return `Move Class` ranked first at **0.563**, with near-identical runners-up
(`Extract Method` 0.500–0.502, `Move And Rename Method` 0.494–0.495). The input varies; the
output does not.

### Q. "Is 103 test examples enough to conclude anything?"

No, and we should not overclaim from it. 686 rows split 480 / 103 / 103. With 18 labels, some
have single-digit support — `Push Down Attribute` has 6 instances in the whole corpus, `Split
Package` 8, `Extract Subclass` 9. Per-label F1 on those is close to meaningless. What the small
test set *can* support is the aggregate claim that the model does not beat the majority-class
prior, because that comparison does not depend on any individual rare label.

### Q. "Was there leakage between train and test?"

**We have not verified this, and I will not claim we have.** The split is random over rows, not
grouped by project or by commit. If multiple rows derive from the same commit or the same class,
related examples can appear on both sides, which would inflate the held-out metrics. Given the
metrics are already at the majority-class baseline, leakage would make the true picture worse, not
better. Checking it with a grouped split is on the immediate list.

### Q. "So is the model useless?"

As a *ranker over refactoring types*, on this training corpus, it carries no information about the
specific smell. That is a measured result, not a guess. It does not follow that the approach is
unworkable — it follows that the training corpus is wrong for the task. 55% of one label is the
first thing to fix.

---

## 5. Causality and inference

### Q. "You applied a refactoring and the count fell. Did the refactoring cause that?"

Not established by that alone, and our tooling refuses to say it did. On a complete Tika run the
system printed `Causal claim allowed: false` with the note "No validated source refactoring was
applied; smell changes must not be attributed to refactoring."

What would license a causal claim: the same module set built before and after, a validated source
change, and the *specific* smell targeted being absent afterwards. The third condition is the one
we almost never meet.

### Q. "What is your control?"

We do not have a randomised control, and that is a real weakness. What we have is a matched
before/after design with everything held constant except the refactoring — same commit, same JDK,
same Maven flags, same Arcan jar, same module set — plus the comparability gate that voids any run
where that does not hold. A stronger design would add a placebo arm: a structurally neutral edit
(say, renaming a private local) put through the identical pipeline, to confirm the measured delta
is zero when nothing architectural changed. We have not run that. It is cheap and we should.

### Q. "Arm C beats Arm B on two systems. Is the planner better?"

On two of three, by small margins, with n = 3. That is not a result you can generalise from. Arm C
reads real cycles from bytecode and prices each move; Arm B takes the model's label and lets the
generator infer a destination. They also do not get the same information, so the comparison is
confounded by design — it tells you that *information about the actual graph helps*, which is
unsurprising, rather than that one ranking method dominates. log4j2 is a tie at −6.

---

## 6. Construct validity

This is the deepest line of attack and the one most students are unprepared for.

### Q. "Why is the number of architectural smells the right dependent variable?"

**It probably is not, and we have evidence from our own data that it is not.** Three findings:

1. **Counting is not measuring.** tika-B7: net change zero, ten smells removed, ten created. A net
   figure scores that identically to tika-B8, where literally nothing changed.
2. **The count can improve while the structure worsens.** tika-C4 reduced the count by 2 while
   taking package cycles from 68 to **73**.
3. **Reductions came from the wrong place.** Of 120 recommendations that reached a comparable
   measurement, the specific smell named was removed in **zero** cases. Counts fell; the targeted
   problems did not.

So smell count is a *proxy*, and a loose one. Better dependent variables would be cycle
participation, cycle size, or change-proneness measured from history — which is precisely what our
"score candidates on cycle participation, not raw count" next step is about.

### Q. "Does reducing smells improve anything a maintainer cares about?"

We have not shown that, and nothing in this project does. That link — smell to defect density, or
smell to change effort — is an empirical claim that would need its own study with history data.
Stating it would be exactly the kind of unsupported claim the pipeline is built to prevent.

### Q. "Are Tika, log4j2 and Struts representative?"

Three Apache Java projects, Maven-built, mature, large. They are representative of *that*, and
nothing more. Not of small codebases, not of Gradle or Bazel builds, not of Kotlin or Scala, not
of commercial code with different review norms. External validity is weak and we should say so
rather than be told.

---

## 7. Defending a negative result

### Q. "Is a well-measured negative result an acceptable contribution?"

Your deck already asks this, which is the right move — it frames it as a methodological question
rather than an excuse. The defence:

1. **It is falsifiable and reproducible.** Every figure comes from a run on one machine against
   named commits with a named detector version, reproducible from committed code.
2. **It is mechanistically diagnosed.** We do not say "it did not work". We say the model scores
   macro-F1 0.039 because 55% of the training corpus is one label; the generator discards 128 of
   277 Tika suggestions because it only understands package granularity while the model names
   classes; and 19 of 56 batches are void because the module set moved.
3. **The infrastructure is a contribution independent of the result.** The comparability gate,
   the identity-level diff and the causal-claim refusal are reusable, and they caught a real error
   in our own measurement.
4. **The alternative is worse.** The same pipeline without those gates would have reported −92% on
   a batch where a module simply failed to compile.

### Q. "What would make you abandon the approach?"

A good examiner asks this to see whether your hypothesis is falsifiable. A defensible answer: if,
after rebalancing the corpus and teaching the generator class granularity, the target-smell
removal rate stays at zero across a larger corpus, then the premise — that a learned type-ranker
plus a graph-aware generator can locate removable architectural smells — is wrong, and the
honest conclusion is that architectural smells are not removable by single-class relocation at
all. Our own data already hints at this: dissolving a dependency cycle was **never** achieved,
here or in two expert-refactored trees.

---

## 8. Engineering specifics

### Q. "Why both OpenRewrite and Spoon?"

OpenRewrite for catalogue recipes and declarative transformation with an LST that preserves
formatting; Spoon for the planned-move experiments, where we needed finer programmatic control
over the AST. Keeping both is a cost, and consolidating is a fair criticism.

### Q. "Why only Move Class?"

Because it is what the model ranks first on essentially every input, and because it is the only
operation whose effect on the dependency graph we can predict before applying it — which is what
makes the planner arm possible. We also tried edge inversion: **1 of 18** attempts succeeded. It
failed six distinct ways, four of them visible in the dependency snapshot before any transformation
was attempted.

### Q. "Where does the destination package come from? The model does not supply one."

Correct, and this is the single most important boundary in the project. A model record contains a
smell name, the affected elements, and five ranked refactoring *type* names with scores. It names
no class to move and no destination. Those parameters come from the repository's own
`generate_recipes.py`, which infers them from reciprocal package dependencies. So a suggestion
constrains *what kind* of change and *where to look*, never *what edit to perform*. Every measured
result is the label plus the generator's inference.

### Q. "Why did combining your two best batches not add up?"

log4j2-B1 measured −6 and B7 measured −1 on distinct counts. Combined, they measured **−6**, not
−7. Smell deltas are not additive because the moves interact through the same dependency graph.
This is why we measured the combination instead of summing it — and it is the same reason an
earlier pair of Long Statement effects cancelled exactly, which would have made a summed figure
right for entirely the wrong reason.

---

## 9. Questions you should want to be asked

Steer toward these. They are where the work is strongest.

- **"Walk me through how you caught the counting error."** Two independent measurements, a
  disagreement of 10 smells, chased rather than rationalised. Ends with 37/37 agreement.
- **"What does your tool do when it achieves nothing?"** It prints `Causal claim allowed: false`
  and fills the delta column with zeros. Most tools find something encouraging to report.
- **"Show me a change that improved on every measure."** tika-C8. One class moved —
  `org.apache.tika.server.core.MetadataList` into `server.core.writer`. Two smells removed, none
  created, package cycles 68 → 67, build green. One batch out of 37.
- **"How do you know your 19 discarded batches were right to discard?"** Because the module-set
  guard is mechanical and checkable, and we publish what each would have claimed.

---

## 10. Three answers to never give

1. **"The improvement was 6.6%."** Not without immediately saying it is 15 smells out of 227 on
   one batch of one system, and that the targeted smell survived. A percentage with no denominator
   invites exactly the follow-up you cannot answer.
2. **"The model works, it just needs more data."** You have not shown more data helps. You have
   shown the corpus is 55% one label. Say *that*.
3. **"We reduced smells."** On two of three systems the model arm reduced nothing at all. The
   precise claim is: one arm, on one system, reduced the distinct count by 6 of 714, and the smell
   it was aimed at is still there.
