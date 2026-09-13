# Smell → Refactoring Recommendation: research program

**Goal:** a suggestion system whose recommendations *measurably remove* the targeted
architectural smell **more than 50% of the time**, and that generalises to repositories it
was not trained on.

Quality of the method matters more than hitting the number. Every claim here must be
traceable to a measurement or a cited source; nothing is estimated or assumed.

---

## The distinction this program is built on

The closest prior work, **ROSE** (arXiv 2507.12561), fine-tunes CodeBERT/CodeT5 on 2M+
refactoring instances from 11,149 Java projects and reports **96.9% accuracy / 95.2% F1** on
a three-class problem (God Class, Cyclic Dependency, Hub-like Dependency).

That metric answers *"which refactoring TYPE is associated with this smell?"*

It does not answer *"did the smell go away?"* — and those come apart badly. Our own
validated pipeline reached a comparable rate on its own terms (13/14 and 47/47 candidates
judged legal, ~90% of agent picks applying cleanly) while producing:

| repo | applied | smells before → after | targeted delta | verdict |
|---|---|---|---|---|
| apache-pdfbox | 7 | 952 → 957 | **+5** | rejected_smells_increased |
| apache-tika | 10 | 314 → 314 | −2 targeted, +2 collateral | rejected_no_reduction |

Both compiled; pdfbox's 38 tests passed. The recommendations were *type-correct and
legal*, and still did not remove smells. **Classification accuracy is not the objective.**

So this program's primary metric is **measured removal rate**, with classification F1
reported only as a secondary comparison against ROSE.

---

## Constraints (from the brief)

- Real examples only. No fabricated code, no invented commits.
- The model must **not** receive whole source files, nor Arcan/Designite output, as training
  input — those cause overfitting to the detector rather than learning the repair.
- RefactoringMiner alone is too small; it is one input among several.
- Compare approaches strictly; generalisation to unseen repos is part of the bar.

## Status

| Phase | State |
|---|---|
| 1. Taxonomy + precedent | done |
| 2. Dataset construction | v1 built; 7 of 20 methods reach the 50/3-repo bar |
| 3. Model | not started |
| 4. Evaluation vs precedent | not started |
| 5. Agent integration | not started |

## Assets already verified on disk

- **25,504 real refactorings** across **13 repositories** (RefactoringMiner output),
  **45 types with ≥50 instances** — a genuine, already-mined corpus.
- A working validation pipeline that compiles, runs the project's own tests, and
  re-measures with Arcan — i.e. a means of producing **outcome labels** that
  classification-only datasets do not have.

## Findings log

- **2026-09-12** ROSE reports 95.2% F1 on smell→refactoring-type classification, but
  reports no smell-removal outcome. Precedent for the classification metric; no precedent
  found yet for a measured removal rate.
- **2026-09-12** Dataset v1: **580 real examples**, 20 methods, 13 repositories, extracted
  from actual commits via `git show` (781 KB). 7 methods reach 50 examples across ≥3 repos;
  Extract Interface — the textbook cycle remedy — has **4**. The corpus limit is the number
  of repositories mined, not the extractor.
- **2026-09-12** Scope correction worth stating plainly: the brief asks for 50 examples per
  smell *and* removal method. 13 repositories do not contain that for most methods. Closing
  the gap means mining more repositories; padding it would mean fabricating examples, which
  the brief forbids and which would be worse than a smaller honest corpus.

---

## Phase 3 result: ranking beats classification, and honesty costs points

Two models, same data, **repository-held-out folds** (never a random split — a random split
lets a project appear in train and test, and then a model that has memorised one project's
conventions scores as though it generalised).

| | v1 corpus (13 repos) | v2 corpus (16 repos) |
|---|---|---|
| Baseline — classification, 16 classes | acc 0.379 · F1 0.367 | **acc 0.272 · F1 0.258** |
| Ranker — which destination | P@1 0.550 · MRR 0.736 | **P@1 0.455 · MRR 0.654** |
| random floor | 0.180 | 0.179 |
| first-candidate heuristic | 0.150 | 0.167 |

**Adding data lowered both scores.** Guava, Karaf and Lucene are unlike the commons-*
projects that dominated v1, so the held-out folds got harder. The v2 numbers are the ones to
quote: v1 flattered itself on a narrow corpus. This is the evaluation working.

**The ranker beats the floors by 2.5×; the classifier does not clear its own ceiling.**
ROSE reports 0.952 F1 on classification with 2M instances; we have 224 usable rows over 16
classes, so 0.258 measures corpus size, not a refuted result. The finding that matters is
that the *same features* rank well and classify poorly — ranking asks a question the
structure can answer.

### Corpus after mining

3,299 architectural instances, 20 methods, 16 repositories; 626 extracted examples; 10
methods at 50 with ≥3-repo spread (was 7). Extract Interface — the textbook cycle remedy —
still has **6**. Six repositories could not be mined at all: they were cloned `depth=1` and
have no history.

### Known gap before the >50% goal can be measured

The ranker's label is *"the destination developers chose"*, not *"the destination that
reduced the smell"*. Those correlate but are not the same, and the difference is the whole
problem: pdfbox's moves were developer-plausible, legal, compiled, passed 38 tests — and
added 5 smells. Only the validation pipeline produces the outcome label, and until the
ranker trains on that, no number here can be read as a removal rate.
