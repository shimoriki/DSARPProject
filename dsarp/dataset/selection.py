"""Select refactoring candidates on features whose direction survives a repository boundary.

Four selection attempts failed before this: detector severity, leaf-first ordering, a
regressor on smell delta, and loosening legality. Each fitted everything available, scored
respectably in aggregate, and collapsed on a held-out repository -- the signature of features
that separate WITHIN a project and point different ways BETWEEN projects.

So screen first, fit second. A feature is kept only if winners and losers differ in the same
direction in every repository that has both outcomes. Fitted on the nine that pass, it looked
like it doubled the shipped ATDI order held out (precision@k 0.21 vs 0.11, random 0.18).

That did NOT survive a pre-registered confirmation on fresh candidates, with the selection frozen
before any outcome existed: model 1/9, shipped 0/9, random 2/9. The held-out number was noise.
The screen is kept because rejecting features that flip sign between repositories is still the
right filter against the failure it targets, but it is not a validated selector.

STATUS: disproved by its own pre-registered confirmation (model 1/9, shipped 0/9,
random 2/9). Kept because the method -- screen features by cross-repository direction
before fitting -- is worth reporting with its failure. No caller by design except its
test, which documents direction_consistent. See docs/negative-results.md.
"""
from __future__ import annotations

import statistics
from typing import Callable, Dict, List, Sequence


def direction_consistent(rows: Sequence[Dict], features: Sequence[str],
                         value: Callable[[Dict, str], float],
                         label: Callable[[Dict], int]) -> List[str]:
    """Features whose winner-minus-loser sign agrees in every repo that has both classes."""
    repos = sorted({r["project"] for r in rows})
    keep = []
    for f in features:
        signs = set()
        for rp in repos:
            sub = [r for r in rows if r["project"] == rp]
            pos = [value(r, f) for r in sub if label(r)]
            neg = [value(r, f) for r in sub if not label(r)]
            if not pos or not neg:
                continue
            d = statistics.mean(pos) - statistics.mean(neg)
            if d:
                signs.add(d > 0)
        if len(signs) == 1:
            keep.append(f)
    return keep
