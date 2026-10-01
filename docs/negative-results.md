# What was tried and did not work

Five attempts to decide *which* refactoring is worth applying. None survived a held-out
repository. The code for each is kept in `dsarp/dataset/`, labelled `STATUS:` at the top of the
module, with no caller by design — deleting it would delete the evidence, and leaving it
unlabelled made an audit read it as live machinery.

This is the project's most defensible finding: the system can apply refactorings correctly and
verify them, and it cannot yet predict which ones are worth applying.

| attempt | where | measured outcome |
|---|---|---|
| 1. Detector severity (ATDI) order | shipped default | anti-predictive: on pdfbox the high-severity half gave 2/12 wins and **+12** smells, the low half 6/13 and **−273**. Worst or tied-worst in every run since. |
| 2. Leaf-first (Mikado Method) | `dataset/mikado.py` | −0.115 against the oracle |
| 3. Regressor on smell delta | `dataset/value_ranker.py`, `dataset/ranker.py` | 0.783 of oracle on pdfbox, 0.25 on log4j2, **−0.786** on tika, where it picks actively harmful candidates |
| 4. Loosening legality (type constraints) | `refactoring/spoon_plan.py` | more legal candidates, net win rate **36% → 9%**: the top-k cut moved down the ranking into marginal candidates |
| 5. Direction-screened feature selection | `dataset/selection.py` | held out at precision@k 0.21 vs shipped 0.11, random 0.18 — then **failed its pre-registered confirmation on fresh candidates: model 1/9, shipped 0/9, random 2/9** |

## Why they failed, as far as the evidence goes

Attempts 2, 3 and 5 were all fitted against **smell-count delta**. A bytecode cycle oracle later
showed that count measures how many elements participate in a handful of giant
strongly-connected components, so the target was dominated by whichever move detached the
largest subtree — one pdfbox move accounts for −240 of the 325 smells ever removed here. A
target that generates outliers that large cannot be generalised from 14–16 wins.

Attempt 5 is the one worth reporting as a method: screen features by whether their direction
survives a repository boundary *before* fitting. It beat both baselines on held-out data and
then did not survive confirmation, which is what pre-registration is for.

## What replaced them

Not a sixth model. The structural effect of a class move is **arithmetic**: relabel the class in
the class-level dependency graph, re-derive the package graph, diff it
(`dsarp/refactoring/move_planner.py`). Predicted versus measured added edges on 18 candidates:
exact on 14, within one on 18. Selection is now a calculation whose claim is checked afterwards
by two independent bytecode readers, not a prediction fitted to a proxy.

## Not a negative result

`dsarp/dataset/smell_methods.py` sits in the same folder and also has no caller, for an
unrelated reason: a human runs it. It produced `data/datasets/smell_methods_v1.json`, which is
committed and described in `docs/smell-refactoring/METHODS.md`.
