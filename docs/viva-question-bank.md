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

---

# Appendix A — Why these tools

An examiner asks this to find out whether a choice was reasoned or inherited. The strongest
answer separates the two honestly, because a post-hoc justification for an inherited default is
easy to spot and expensive when spotted.

## The short version

| Tool | Version | Why it, specifically |
|---|---|---|
| **Arcan** | 1.2.1 | Reads **bytecode**, so it sees the graph that actually links, including dependencies the source does not make obvious. Independent of whether sources parse. |
| **DesigniteJava** | 2.9.1 Pro | Reads **source**, so it sees implementation and design smells that do not survive compilation — long statement, magic number, complex conditional. Complementary to Arcan, not redundant. |
| **RefactoringMiner** | 3.1.4 | Mines refactorings maintainers *actually performed* from commit history. The only source of ground-truth labels in the project. |
| **OpenRewrite** | 6.46.1 | Transforms via a **Lossless Semantic Tree**: type-aware and formatting-preserving, so a recipe changes what it targets and nothing else. |
| **Spoon** | 10.4.2 | Finer programmatic AST control, used for planned-move experiments where we needed a move's effect computed before applying it. |
| **jdeps + ArchUnit** | JDK / lib | Two *independent* readings of the dependency graph, cross-checking the edge oracle. jdeps agreed with the oracle on 13 of 13 verdicts it could read. |
| **Maven** | 3.9.9 | Not a choice. Tika, log4j2 and Struts are Maven projects. |

## The questions behind the question

### "Why detect smells twice, with two tools?"

They answer different questions and neither subsumes the other. Arcan works from compiled classes
and reports **architectural** smells — cycles, hubs, unstable dependencies — properties of the
dependency graph. Designite works from source and reports **implementation and design** smells,
properties of code inside a class.

Sharpest evidence they are not interchangeable: commons-validator has **18** architectural smells
and **201** implementation smells. Same repository, same commit, both correct.

### "Why bytecode rather than source for the architecture?"

Bytecode reflects what actually links, so it catches dependencies introduced through inheritance
chains, generics and framework glue that a source reader can miss. It does not require sources to
parse, which matters in a multi-module reactor where some modules fail. And it gives one uniform
graph regardless of source style.

Concede the cost: the compiler erases generics, synthesises bridge methods and desugars lambdas,
so the bytecode graph is not the design-level graph. We hold it constant — same JDK, same flags,
same jar for every before/after pair — so the *difference* stays attributable to the refactoring.
We cannot claim the absolute graph equals the source design.

### "Why two transformation engines?"

OpenRewrite for catalogue recipes and declarative transformation; Spoon where a move's graph
effect had to be computed programmatically before applying it. Carrying both is a real cost and
consolidating is fair criticism. The defensible part is that they did different jobs.

### "Why jdeps AND ArchUnit AND your own oracle?"

Because one tool saying "the edge is gone" is an assertion, and three agreeing is evidence. Same
reasoning that caught the UD30 bug: independent measurements that disagree are informative, and
the project is built to notice when they do.

---

# Appendix B — Why DistilBERT

## Be honest about provenance first

**DistilBERT was inherited, not selected.** It comes from the supplied repository's own notebook
recipe; we trained it here on the supplied dataset rather than choosing it after a comparison.
Say that. Then give the justification, clearly labelled as post-hoc.

## Why it is nevertheless defensible

**The task shape.** Input is one sentence describing a smell plus its metrics. Output is a set of
refactoring type labels, more than one of which can apply. That is **multi-label text
classification over short inputs** — exactly what a pretrained encoder with a classification head
is for.

**The data size.** 686 labelled rows. Far too little to train a transformer from scratch, so
transfer learning is close to mandatory. Also small enough that a full BERT's extra capacity buys
nothing and overfits sooner.

**What distillation buys.** DistilBERT is a student trained to reproduce BERT-base's behaviour
(Sanh et al., 2019). Six transformer layers instead of twelve, same width (768) and head count
(12), roughly 66M parameters against 110M — about **40% smaller and 60% faster**, retaining
roughly **97%** of BERT-base's GLUE performance. On 686 rows on one laptop, that trade is clearly
correct.

**Our actual configuration**, from `config.json` and `labels.json`:

```
DistilBertForSequenceClassification
problem_type        multi_label_classification
n_layers 6 · dim 768 · n_heads 12 · vocab 30522 (WordPiece, uncased)
max_length 256 · batch size 4 · 5 epochs
```

## The alternatives, and what each would have given

| Alternative | What it would buy | Why it would not fix our problem |
|---|---|---|
| **BERT-base / RoBERTa** | ~3% more GLUE, more capacity | Our bottleneck is a corpus that is 55% one label. More capacity learns that prior faster, not better. |
| **TF-IDF + logistic regression** | Interpretable, trivially fast, a real baseline | **We should have run this.** It is the missing control: if it matches macro-F1 0.039, the transformer adds nothing, and that is worth knowing. |
| **CodeBERT / GraphCodeBERT** | Pretrained on code rather than prose | Genuinely better-matched family — but our input is a natural-language smell description, not source, so the advantage is smaller than it first looks. Worth trying. |
| **An LLM, zero- or few-shot** | No training corpus needed | Does not address the real boundary: the output would still be a refactoring *type*, not a class and a destination. |
| **Rules over graph metrics** | No ML at all, fully explainable | Arguably the right baseline. Our Arm C planner is close to this, and it beats the model arm on two of three systems. |

## The two answers that win marks here

**1. The model is not the bottleneck the architecture implies.** Even a perfect type-ranker would
not produce a refactoring. A record contains a smell name, the affected elements, and five ranked
refactoring *types*. It names no class to move and no destination; those come from the generator's
inference over reciprocal package dependencies. The model constrains *what kind* of change and
*where to look*, never *what edit to perform*.

**2. Our own training evidence says stop tuning and fix the corpus.** The best checkpoint was at
**step 120 — epoch 1 of 5**, selected on micro-F1. Four further epochs made it worse. A model that
peaks after one pass over 480 examples and then degrades has learned the label prior almost
immediately. That is a data problem, and no architecture swap fixes it.

---

# Appendix C — The mathematics

## C.1 Graph theory — what a cycle actually is

Model the system as a directed graph `G = (V, E)`, `V` the packages (or classes), an edge
`u → v` meaning *u depends on v*.

A **cyclic dependency** is a **strongly connected component** (SCC) of size ≥ 2: a maximal vertex
set where every vertex reaches every other. Found in `O(|V| + |E|)` by Tarjan's algorithm.

Two consequences that matter for our results:

- **Removing one edge rarely removes a cycle.** An SCC survives until every return path is cut. An
  edge whose removal splits the SCC is a bridge *in the condensation*; most edges are not. This is
  why 18 of 18 moves removed their target edge while 0 of 120 targeted smells disappeared.
- **Contracting each SCC to a single node gives the condensation**, always a DAG. The **Acyclic
  Dependencies Principle** is the statement that the package graph should already be that DAG.

## C.2 Martin's package metrics

For a package, `Ca` afferent coupling (incoming) and `Ce` efferent (outgoing):

```
Instability      I = Ce / (Ca + Ce)             ∈ [0, 1]
Abstractness     A = abstract types / all types ∈ [0, 1]
Distance         D = | A + I − 1 |
```

`I = 0` is maximally stable (everyone depends on it, it depends on nothing); `I = 1` maximally
unstable. `D` is distance from the "main sequence" `A + I = 1`, where a package is as abstract as
it is stable.

**Stable Dependencies Principle (SDP):** depend in the direction of increasing stability — a
package should not depend on one with higher `I`. An **unstable dependency** smell is an SDP
violation.

**Worked from our data:** `org.apache.commons.validator.util` has `I = 0.84` and depends on
`org.apache.commons.validator` at `I = 0.845` — something *less* stable, so it is flagged.
`UD30.csv` is the same relation filtered at a 30% threshold, a severity view, which is exactly why
counting it separately double-counted.

## C.3 Multi-label classification

**Why not softmax.** Softmax forces `Σ p_i = 1`, asserting mutually exclusive labels. A smell can
warrant several refactorings at once, so each label gets an independent **sigmoid**:

```
σ(z) = 1 / (1 + e^(−z))
```

**Loss** is binary cross-entropy over `L` labels (HuggingFace selects `BCEWithLogitsLoss`
automatically for `problem_type = multi_label_classification`):

```
ℒ = −(1/L) Σ_l [ y_l · log σ(z_l) + (1 − y_l) · log(1 − σ(z_l)) ]
```

Predictions are binarised at a threshold, conventionally 0.5.

## C.4 Why macro-F1 is the honest metric — with the arithmetic

```
Precision  P = TP / (TP + FP)
Recall     R = TP / (TP + FN)
F1          = 2PR / (P + R)        harmonic mean — punishes imbalance between P and R
```

- **Micro-average:** pool TP, FP, FN across all labels, *then* compute F1. Dominated by frequent
  labels.
- **Macro-average:** compute F1 per label, then take the unweighted mean. Every label counts
  equally regardless of support.

**The decisive calculation.** `Move Class` is 381 of 686 rows (55.5%). Consider a classifier that
answers "Move Class" and nothing else:

```
P = 0.555   R = 1.0
F1(Move Class) = 2(0.555)(1.0) / 1.555 = 0.714
F1(other 17 labels) = 0
macro-F1 = 0.714 / 18 ≈ 0.0397
```

Our model scores **0.0387** — level with, fractionally below, a classifier that ignores its input
entirely. Micro-F1 0.353 and top-5 hit rate 0.913 both look respectable because both are flattered
by the majority class. This is the most important number in the project, and you should be able to
derive it at the board.

## C.5 Smell identity as set matching

A smell has no stable identifier across runs — Arcan numbers cycles `Cycle0, Cycle1…` in detection
order, and those shift whenever anything changes. So identity is structural:

```
cyclic dependency   ≡  the frozenset of its member components
unstable dependency ≡  the ordered pair (package, correlated package)
hub-like            ≡  the class
```

Matching a model's named elements `K` against an Arcan cycle with members `M` uses

```
| M ∩ K | ≥ 2
```

The threshold is 2 because a cycle needs at least two participants, and because Arcan's cycle may
be a **subset or a superset** of the elements the model listed — equality would be far too strict,
a single shared element far too loose.

Set difference across two runs then gives genuine removals and creations, which is how tika-B7 was
shown to have swapped ten smells for ten others while its net read zero.

---

# Appendix D — Architectural concepts

| Concept | Where it appears | What to say |
|---|---|---|
| **C4 model** | The architecture slides | Simon Brown's Context / Container / Component / Code. We use the first three; Code adds nothing the source does not. |
| **Pipes and filters** | The 13-stage console pipeline | Each stage has typed inputs and outputs and records what it consumed, called and produced, so a run is auditable after the fact. |
| **Adapter pattern** | `EvidenceAdapter` → `ArcanAdapter` | Isolates the system from any one detector's CSV schema; swapping detectors changes one class. Own the irony: the UD30 bug lived in exactly this adapter. |
| **Oracle pattern** | Bytecode edge oracle, cross-read by jdeps | An independent judge of whether a transformation achieved its structural goal, separate from the thing that performed it. |
| **Martin's package principles** | The smell definitions | ADP (acyclic), SDP (depend toward stability), SAP (as abstract as it is stable). Our three Arcan smell types map onto ADP and SDP violations. |
| **LST vs AST** | OpenRewrite vs Spoon | A Lossless Semantic Tree preserves formatting and type information, so a transformation is byte-identical outside its target. A plain AST discards formatting. |
| **Separation of concerns** | Evidence / Transformation / Validation / Measurement | The central design claim: the thing that proposes a change must not be the thing that judges it. |
| **Quasi-experimental design** | Every batch | Matched before/after, everything constant except the refactoring, plus a comparability gate voiding a run when the module set moves. No randomisation, hence quasi-experimental. |
| **Knowledge distillation** | DistilBERT | A compact student trained to reproduce a larger teacher's output distribution. |
| **Self-attention** | The transformer | `Attention(Q, K, V) = softmax(QKᵀ / √d_k)V`. The `√d_k` scaling keeps dot products out of the softmax's saturated region, where gradients vanish. |

## The one architectural claim to lead with

The system separates four kinds of statement, and only the last two license the sentence *"this
refactoring helped"*:

1. What the detector found — an observation.
2. What the model suggests — a hypothesis.
3. What was applied and compiled — an intervention.
4. What the detector found afterwards on an equivalent build — a measurement.

Most tooling in this space collapses 2 into 4. The console printing `Causal claim allowed: false`
is that separation made executable.
