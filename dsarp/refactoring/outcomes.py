"""What each suggestion type has ACTUALLY achieved, measured across every verified run.

The planner's ordering was built from reasoning about what ought to work. Reading the
verified runs back shows that reasoning was wrong in three places:

    smell / refactoring                       runs   net effect
    Cyclic Dependency  / Merge Package           9        -7     works
    Unstable Dependency/ Move Class              5        -8     works
    God Component      / Split Package          11        -4     works
    Deficient Encaps.  / Encapsulate Field       4         0     never reduced anything
    Scattered Funct.   / Consolidate Package     4         0     never reduced anything
    Wide Hierarchy     / Introduce Supertype     3        +2     made things WORSE

Two of those matter for suggestion quality. Encapsulate Field and Consolidate Package are
safe and compile cleanly, so every gate passed them — they simply never move the number.
Introduce Supertype is worse than useless: it adds a type the detector then counts.

`resolves_fully` also did not predict success the way the ranking assumed: partial God
Component splits net -3 over 4 runs while "full" ones net -1 over 7.

So this module reads the outcome ledger out of past runs and lets the planner rank by
measured effect instead of by assumption. Evidence the system produced about itself, used
the same way tool findings are: as fact, not preference.
"""
from __future__ import annotations

import collections
import glob
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# A refactoring needs at least this many verified runs before its record is trusted. Below
# it, absence of measured benefit is just absence of evidence.
MIN_RUNS = 3


def build_ledger(outputs_dir: Path) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Aggregate (smell_type, refactoring) -> measured effect over verified runs.

    Only runs whose build COMPILED are counted: a delta from a tree that does not compile is
    not evidence of anything, the same rule the verification gate applies everywhere else.
    """
    stat: Dict[Tuple[str, str], Dict[str, Any]] = collections.defaultdict(
        lambda: {"runs": 0, "reduced": 0, "net": 0})
    for f in glob.glob(str(Path(outputs_dir) / "*" / "openrewrite_loop_report.json")):
        try:
            r = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if r.get("build_after_refactoring") != "compiled":
            continue
        delta = r.get("delta_by_type") or {}
        for p in r.get("plans") or []:
            if not p.get("applicable"):
                continue
            d = delta.get(p.get("smell_type"))
            if d is None:
                continue
            s = stat[(p["smell_type"], p.get("refactoring") or "?")]
            s["runs"] += 1
            s["net"] += d
            s["reduced"] += 1 if d < 0 else 0
    return dict(stat)


def expected_effect(ledger: Dict[Tuple[str, str], Dict[str, Any]],
                    smell_type: str, refactoring: str) -> Optional[float]:
    """Mean measured change per run. Negative is good. None when there is too little data."""
    s = ledger.get((smell_type, refactoring))
    if not s or s["runs"] < MIN_RUNS:
        return None
    return s["net"] / s["runs"]


def is_counterproductive(ledger: Dict[Tuple[str, str], Dict[str, Any]],
                         smell_type: str, refactoring: str) -> bool:
    """True when this suggestion has been measured to make the count WORSE.

    Introduce Supertype is the case that motivated this: it compiles, passes every safety
    gate, and adds a type the detector counts — so the run comes out worse than it started.
    A suggestion that reliably harms is not a quality suggestion, however safe it is.
    """
    e = expected_effect(ledger, smell_type, refactoring)
    return e is not None and e > 0


def has_no_measured_benefit(ledger: Dict[Tuple[str, str], Dict[str, Any]],
                            smell_type: str, refactoring: str) -> bool:
    """True when enough runs exist and none of them ever reduced the smell."""
    s = ledger.get((smell_type, refactoring))
    return bool(s) and s["runs"] >= MIN_RUNS and s["reduced"] == 0


def summarise(ledger: Dict[Tuple[str, str], Dict[str, Any]]) -> list:
    """Rows for the dashboard: what the system has learned about its own suggestions."""
    rows = []
    for (smell, refac), s in sorted(ledger.items(), key=lambda kv: kv[1]["net"]):
        mean = s["net"] / s["runs"] if s["runs"] else 0.0
        rows.append({
            "smell type": smell, "refactoring": refac,
            "verified runs": s["runs"], "runs that reduced": s["reduced"],
            "net effect": s["net"], "mean per run": round(mean, 2),
            "verdict": ("counterproductive" if s["runs"] >= MIN_RUNS and mean > 0
                        else "no measured benefit" if s["runs"] >= MIN_RUNS and s["reduced"] == 0
                        else "effective" if s["reduced"] else "too few runs"),
        })
    return rows
