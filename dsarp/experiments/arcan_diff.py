"""Which individual Arcan smells a change removed, and which it created.

A count says a tree went from 260 smells to 243. It does not say whether the same 243 survived
and 17 vanished, or whether 40 vanished and 23 new ones appeared in their place. Those are very
different refactorings and this project has measured both, so the comparison has to be by
identity rather than by total.

Identity per smell type, taken from Arcan 1.2.1's own output:

    Cyclic Dependency   the SET of packages (or classes) in the cycle, from the membership
                        matrix. A cycle that merely lost a member is a different cycle, not a
                        survivor -- and not a new one either, which `shrunk` records separately.
    Unstable Dependency the (unstable package, correlated package) pair, from UD.csv and UD30.csv.
    Hub-Like Dependency the class, from HL.csv.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

CYCLE_FILES = {"package": "packageCyclicDependencyTable.csv",
               "class": "classCyclicDependencyTable.csv"}


def _rows(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def cycle_sets(arcan_dir: Path, level: str) -> Set[frozenset]:
    """Each cycle as the frozen set of its members, read from the membership matrix."""
    path = Path(arcan_dir) / CYCLE_FILES[level]
    if not path.is_file():
        return set()
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    if len(rows) < 2:
        return set()
    header = rows[0]
    out = set()
    for row in rows[1:]:
        members = frozenset(header[i] for i in range(1, min(len(row), len(header)))
                            if str(row[i]).strip() == "1")
        if members:
            out.add(members)
    return out


def unstable_pairs(arcan_dir: Path) -> Set[Tuple[str, str]]:
    out = set()
    for name in ("UD.csv", "UD30.csv"):
        for r in _rows(Path(arcan_dir) / name):
            pkg = (r.get("UnstableDependenciesPackage") or "").strip()
            dep = (r.get("CorrelatedPackage") or "").strip()
            if pkg:
                out.add((pkg, dep))
    return out


def hubs(arcan_dir: Path) -> Set[str]:
    return {(r.get("Class") or "").strip() for r in _rows(Path(arcan_dir) / "HL.csv")
            if (r.get("Class") or "").strip()}


def diff(before_dir: Path, after_dir: Path) -> Dict[str, Any]:
    """Smell-level difference between two Arcan runs."""
    out: Dict[str, Any] = {}
    total_removed = total_added = 0
    for level in ("package", "class"):
        b, a = cycle_sets(before_dir, level), cycle_sets(after_dir, level)
        gone, new = sorted(b - a, key=len), sorted(a - b, key=len)
        # a surviving cycle that merely lost members is neither removed nor new
        shrunk = [(sorted(g), sorted(n)) for g in gone for n in new if n < g]
        out["%s_cycles" % level] = {
            "before": len(b), "after": len(a),
            "removed": [sorted(s) for s in gone], "introduced": [sorted(s) for s in new],
            "shrunk": shrunk[:20]}
        total_removed += len(gone)
        total_added += len(new)
    b, a = unstable_pairs(before_dir), unstable_pairs(after_dir)
    out["unstable"] = {"before": len(b), "after": len(a),
                       "removed": sorted(b - a), "introduced": sorted(a - b)}
    total_removed += len(b - a)
    total_added += len(a - b)
    bh, ah = hubs(before_dir), hubs(after_dir)
    out["hub_like"] = {"before": len(bh), "after": len(ah),
                       "removed": sorted(bh - ah), "introduced": sorted(ah - bh)}
    total_removed += len(bh - ah)
    total_added += len(ah - bh)
    out["totals"] = {"smells_removed": total_removed, "smells_introduced": total_added,
                     "net": total_added - total_removed}
    return out


def summarise(d: Dict[str, Any], limit: int = 4) -> List[str]:
    """A few human-readable lines naming the actual smells that moved."""
    lines: List[str] = []
    for level in ("package", "class"):
        c = d["%s_cycles" % level]
        for s in c["removed"][:limit]:
            lines.append("removed %s cycle of %d: %s" % (level, len(s), ", ".join(s[:4])
                                                         + (" ..." if len(s) > 4 else "")))
        for s in c["introduced"][:limit]:
            lines.append("NEW %s cycle of %d: %s" % (level, len(s), ", ".join(s[:4])
                                                     + (" ..." if len(s) > 4 else "")))
    for p in d["unstable"]["removed"][:limit]:
        lines.append("removed unstable dependency: %s -> %s" % p)
    for p in d["unstable"]["introduced"][:limit]:
        lines.append("NEW unstable dependency: %s -> %s" % p)
    for h in d["hub_like"]["removed"][:limit]:
        lines.append("removed hub-like: %s" % h)
    for h in d["hub_like"]["introduced"][:limit]:
        lines.append("NEW hub-like: %s" % h)
    return lines
