"""Spoon's verdict on a mixed plan: the moves applied, then each inversion prechecked on the
moved tree, because a move changes what the interface may legally name.

One `invertEdge` edit per implementation type, not one per package pair. Spoon's
`groupPartition` calls a group legal when ANY of its types is invertible, so a precheck of a
group cannot tell a whole inversion from a partial one, and a partly inverted edge survives.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List

from ..refactoring.strategies import SourceFacts
from ..tools.spoon_runner import precheck_by_module
from ..verification.effect_checker import _copy_repo


def to_edits(inversions: List[List[str]], moves: List[List[str]]) -> List[Dict[str, Any]]:
    """invertEdge edits for the moved tree: an implementation that moved goes by its new name."""
    where = {c: "%s.%s" % (d, c.rsplit(".", 1)[1]) for c, d in moves}
    out = []
    for consumer, impl in sorted(map(tuple, inversions)):
        fqn = where.get(impl, impl)
        out.append({"op": "invertEdge", "type": fqn, "types": [fqn], "toPackage": consumer})
    return out


def dry_run(repo: Path, plan: Dict[str, Any], work: Path) -> Dict[str, Any]:
    """{"ok", "refused", "why"}: moves by Spoon, as `make_plans` checks them, then inversions."""
    from .scc_dissolve import _apply
    shutil.rmtree(work, ignore_errors=True)
    copy = _copy_repo(repo, work / "copy")
    try:
        if plan.get("moves"):
            done = _apply(copy, plan["moves"], work, "spoon")
            if not done["applied"]:
                return {"ok": False, "refused": done.get("refused"), "why": done.get("why")}
        edits = to_edits(plan.get("inversions") or [], plan.get("moves") or [])
        if not edits:
            return {"ok": True, "refused": None, "why": None}
        res = precheck_by_module(copy, edits, SourceFacts(copy), log_dir=work)
        bad = res.get("illegal") or []
        if bad or len(res.get("legal") or []) != len(edits):
            first = bad[0] if bad else {"edit": {}, "why": "not every inversion was judged"}
            return {"ok": False, "refused": first["edit"].get("type"), "why": str(first.get("why"))[:300]}
        return {"ok": True, "refused": None, "why": None}
    finally:
        shutil.rmtree(work, ignore_errors=True)
