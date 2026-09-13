# Architectural smell removal methods: what each one does, and when it works

Companion to `PROGRESS.md`. Every method below is one the dataset carries **real examples
of**, extracted from commits that actually happened. Counts are from
`data/datasets/smell_methods_v1.json`.

The smell→method mapping is taken from the published catalogue — Suryanarayana, Samarthyam
and Sharma, *Refactoring for Software Design Smells* (25 smells, 60+ strategies, and the
source of Designite's smell names, one of whose authors wrote the tool) and the Arcan smell
definitions. It is **not** inferred from our own runs; our runs supply the outcome evidence
at the end of each entry, which is a different thing and frequently disagrees.

---

## The thing this document exists to record

A method being *documented* to address a smell, and a method *actually removing* that smell
in a given codebase, are separate claims. The prior art conflates them: ROSE reports 95.2%
F1 on choosing the right method type and never measures removal. Our own measured runs:

| repo | method | applied | smells | targeted delta | outcome |
|---|---|---|---|---|---|
| apache-pdfbox | Move Class ×7 | yes, compiled, 38 tests passed | 952 → 957 | **+5** | made it worse |
| apache-tika | Move Class ×10 | yes, compiled | 314 → 314 | −2 targeted, +2 collateral | net zero |

Both were type-correct by the catalogue. Both failed. Each entry below therefore separates
**what the method is for** from **what we have measured it doing**.

---

## Relocation methods

### Move Class — 50 examples, 10 repositories

**Targets:** Cyclic Dependency, God Component, Feature Concentration, Scattered
Functionality, Unstable Dependency, Hub-Like Dependency.

**Mechanism.** Relocates a top-level type to another package and repoints every reference.
For a dependency cycle A→B→A, moving the class in A that is responsible for the A→B edge
into B removes that edge; the cycle breaks if no other edge sustains it.

**Preconditions** (each one we learned by a build failing):
- the type must be `public`, or its old package must stop using it;
- its *members* used by the old package must be `public`/`protected` — a public class with
  a package-private constructor still breaks its former neighbours;
- it must not depend on package-private types, fields or methods left behind;
- source and destination must be in the same build module;
- nested types travel with the outer class, and a type's own members are never blockers.

**Measured.** This is the method both failing runs above used. Moving a class *into* a
package that already depends on it relocates the edge rather than removing it — which is
how pdfbox gained 2 cyclic and 3 unstable smells. **Direction matters more than legality.**

### Move And Rename Class — 12 examples, 5 repositories

As above, with a rename. Below the 50 bar in this corpus. Same preconditions; the rename
adds no architectural effect and exists mainly to fit destination naming conventions.

### Move Method — 50 examples, 9 repositories

**Targets:** Feature Envy, Scattered Functionality, Cyclic Dependency.

**Mechanism.** Moves a method to the class whose data it actually uses. Removes a
dependency edge when the method was the only reason its owner referenced the target.

**Preconditions.** Call sites must be updated; the method must not rely on package-private
state of its origin; overrides and interface contracts constrain it. Harder than Move Class
because the unit is smaller and the reference graph denser — our driver does not implement
it, and the retarget pass it would need is the same one that took four attempts for classes.

### Move And Rename Method — 49 examples, 8 repositories

As above. Notable because it was the **top-1 prediction on 658 of 716 log4j2 rows** from the
existing transformer — a method the executor cannot perform, which is precisely why that
model produced no actionable output.

### Move Attribute — 47 examples, 5 repositories

**Targets:** Feature Envy, Broken Modularization. Moves a field to the class that uses it.
Lowest repository spread of the ≥47 group; 5 repos is thin for generalisation.

### Extract And Move Method — 50 examples, 5 repositories

**Targets:** Feature Envy, Insufficient Modularization. Two operations composed: extract a
fragment, then relocate it. The most common architectural refactoring in the corpus after
access-modifier changes (809 real instances), but concentrated in 5 repositories.

---

## Decomposition methods

### Extract Class — 47 examples, 8 repositories

**Targets:** Insufficient Modularization, God Component, Multifaceted Abstraction.

**Mechanism.** Splits one type into two along a cohesive subset of fields and methods. The
direct remedy for a class doing several unrelated jobs.

**Caveat we have measured indirectly.** Splitting creates a new type and often a new
package, and Designite flags new packages as Feature Concentration — a split can reduce one
smell and create another. This is the collateral-delta case the pipeline now reports
separately, and the reason a single total is misleading.

### Extract Superclass — 16 examples, 6 repositories
### Extract Subclass — 5 examples, 2 repositories
### Extract Interface — 4 examples, 3 repositories

**Targets:** Duplicate Abstraction, Broken Hierarchy (super/sub); Cyclic Dependency,
Unstable Dependency, Broken Modularization (interface).

Extract Interface is the textbook remedy for a dependency cycle — invert the edge through an
abstraction — and the corpus has **4 real instances**. It is the clearest case where the
local data cannot support the method the literature most recommends, and it is a concrete
argument for mining more repositories rather than training on what happens to be here.

### Split Package — 1 example · Merge Class — 1 example · Rename Package — 3 examples

Recorded for completeness. Not usable as training signal at these counts.

---

## Hierarchy methods

### Pull Up Method — 50 examples, 9 repositories
### Pull Up Attribute — 50 examples, 7 repositories

**Targets:** Duplicate Abstraction, Broken Hierarchy. Moves a member shared by siblings into
their common supertype. Well represented and well spread — among the better-supported
methods in this corpus.

### Push Down Method — 28 examples, 3 repositories
### Push Down Attribute — 9 examples, 1 repository

**Targets:** Unnecessary Abstraction, Broken Hierarchy. Push Down Attribute comes from a
single repository and must not be used as a training label — one project's conventions are
not a pattern.

---

## Encapsulation methods

### Encapsulate Attribute — 50 examples, 11 repositories

**Targets:** Deficient Encapsulation (967 instances in the Designite corpus).

**Mechanism.** Makes a field private and routes access through accessors. **The best-spread
method in the dataset** at 11 repositories, and subtractive in nature — it narrows
visibility rather than moving code, so it cannot relocate a dependency edge the way a move
can. That makes it low-risk but also architecturally limited.

### Change Class Access Modifier — 50 examples, 4 repositories

**Targets:** Deficient Encapsulation, Unutilized Abstraction. The single most common
architectural refactoring in the corpus (810 instances) but from only 4 repositories after
the spread cap — a warning sign for generalisation.

---

## What the corpus does and does not support

| Tier | Methods | Status |
|---|---|---|
| Usable (≥47 examples, ≥7 repos) | Move Class, Move Method, Move And Rename Method, Pull Up Method, Pull Up Attribute, Encapsulate Attribute, Extract Class | trainable |
| Marginal (≥47 examples, ≤5 repos) | Extract And Move Method, Move Attribute, Change Class Access Modifier | risk of learning one project's style |
| Insufficient (<30 examples) | Push Down ×2, Extract Superclass/Subclass/Interface, Move Source Folder, Split Package, Merge Class, Rename Package | needs more repositories mined |

**580 real examples, 20 methods, 13 repositories.** Seven methods reach the requested 50
with good spread. The gap is not a defect in the extraction — it is what 13 repositories
contain, and closing it means mining more of them.

---

## Consequence for the recommender

The dataset supports learning *which method* fits a smell. It does not, on its own, teach
*which specific instance* of that method will reduce the count — and the measured evidence
says that is where the difficulty lives. A recommender trained only on (smell → method)
pairs reproduces ROSE's result: high classification accuracy, unmeasured effect.

The outcome field exists for that reason, and is filled only by the validation pipeline:
compile, run the project's own tests, re-measure with Arcan, and record the targeted and
collateral deltas separately.
