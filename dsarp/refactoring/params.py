"""Tunable refactoring-policy parameters — the SkillOpt optimisation surface.

Every value here was originally a constant I picked by hand inside a strategy, and several
of them visibly changed outcomes during development (the God Component size floor, the
Unstable Dependency crossing-class cutoff). They are the policy, separated from the
mechanism, so they can be tuned against a measured reward instead of intuition.

The reward already exists and is fully automatic — the closed loop reports
`verification_status == "verified"` (the refactored code still builds) plus the real
before/after smell delta from Arcan and Designite. That is the validation gate; a parameter
set that breaks the build or fails to reduce smells is rejected, exactly like a rejected
skill edit.

Loaded from `configs/refactoring_params.json` when present, so a tuned set can be deployed
without touching code. `SEARCH_SPACE` declares what a tuner may vary and within what bounds.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Dict


@dataclass
class RefactoringParams:
    # -- God Component: when is a package big enough to split, and how big must a
    #    cohesive group be before extracting it is worth the churn?
    god_component_min_classes: int = 6
    god_component_min_group: int = 3

    # -- Unstable Dependency: above this many crossing classes, relocation stops being a
    #    refactoring and becomes a rewrite, so the finding is reported instead.
    unstable_max_crossing: int = 6

    # -- Cyclic Dependency: caps on how much one pass may restructure.
    max_package_merges: int = 4
    max_class_moves: int = 30

    # -- Unutilized Abstraction: delete only with this many external references or fewer.
    dead_code_max_references: int = 0

    # -- Deficient Encapsulation: narrow a field only if at most this many other files
    #    could be reading it (0 keeps it strictly safe).
    encapsulate_max_external_readers: int = 0

    # -- Dead code: may an UNREFERENCED public type be removed?
    #    Every refactoring runs on a COPY, never the user's checkout, so "it is public API"
    #    is an argument about downstream consumers rather than about this repository. With
    #    it enabled, removal still requires zero references inside the repo and non-test
    #    code — the type is provably unused HERE. Disable when the target is a published
    #    library whose API surface is the product.
    remove_unreferenced_public_types: bool = True

    # -- Iterative loop
    max_passes: int = 5

    @classmethod
    def load(cls, path: Path | None = None) -> "RefactoringParams":
        path = Path(path) if path else _default_path()
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: Path | None = None) -> Path:
        path = Path(path) if path else _default_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return path

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _default_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "configs" / "refactoring_params.json"


# What a tuner is allowed to vary, and the values it may try. Bounds are deliberately tight:
# these are safety-relevant, and the point is to find a better policy, not an unsafe one.
# `encapsulate_max_external_readers` and `dead_code_max_references` are intentionally NOT
# included — raising either trades correctness for a better-looking score, which is exactly
# the kind of reward hacking the validation gate should not have to catch.
SEARCH_SPACE: Dict[str, list] = {
    "god_component_min_classes": [4, 6, 8, 12],
    "god_component_min_group": [2, 3, 4, 5],
    "unstable_max_crossing": [3, 6, 10, 15],
    "max_package_merges": [2, 4, 8],
    "max_class_moves": [15, 30, 50],
}

DEFAULTS = RefactoringParams()
