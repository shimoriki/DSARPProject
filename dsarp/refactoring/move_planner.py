"""Moves whose structural effect is computed before anything is applied.

Five ranking attempts have been fitted to Arcan's smell delta and none survived a fresh
repository. This is not a sixth: the effect of moving a class is not a quantity to be
predicted from features, it is a relabelling of one node in a graph we already have. Move the
class in the class-level graph, re-derive the package graph, and read off which package edges
appear and which disappear.

Two facts make that exact rather than approximate:
  * the class-level graph comes from `jdeps -verbose`, which unlike every package-level view
    keeps same-package dependencies -- the ones that decide the cost, because a class leaving
    its package turns each tie to its old neighbours into a package edge;
  * the result is checked against the compiled bytecode afterwards, so a wrong prediction is
    caught rather than believed.

Checked against a measured case: moving PDGraphicsState into contentstream.operator.color was
predicted to leave the targeted edge in place and add twelve edges; measured, it left the edge
in place and added eleven. Moving Loader into pdmodel was predicted to remove the edge and add
exactly two; measured, it removed the edge and added exactly those two.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ..tools.jdeps_runner import move_effect


def in_cycle_edges(snapshot: Dict[str, Any]) -> Set[Tuple[str, str]]:
    """Package pairs that sit inside the same cycle. Only these are worth attacking."""
    out: Set[Tuple[str, str]] = set()
    for comp in snapshot.get("cycles") or []:
        s = set(comp)
        out |= {(a, b) for a in s for b in s if a != b}
    return out


def _sides(edge: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    pairs = [p for p in (edge.get("carriers") or []) if " -> " in p]
    consumers = sorted({p.split(" -> ")[0].split("$")[0] for p in pairs})
    targets = sorted({p.split(" -> ")[1].split("$")[0] for p in pairs})
    return consumers, targets


def plan_moves(snapshot: Dict[str, Any], class_graph: Dict[str, Any],
               accept: Optional[Callable[[str, str, str], bool]] = None,
               limit: int = 20) -> List[Dict[str, Any]]:
    """Moves that remove an in-cycle edge and leave fewer package edges, best net first.

    Only edges carried by a single class on one side are considered: with two carriers the
    move is a package merge in disguise, and the caller has no operation for it.

    `accept(class_fqn, from_package, to_package)` rejects what this repository cannot apply --
    a class with no source here, or a destination in a different Maven module, where the file
    would land where the build cannot see it.
    """
    edges = snapshot.get("edges") or []
    cyclic = in_cycle_edges(snapshot)
    seen: Set[Tuple[str, str]] = set()
    out: List[Dict[str, Any]] = []
    for e in edges:
        pair = (e["from"], e["to"])
        if pair not in cyclic:
            continue
        consumers, targets = _sides(e)
        # Moving the sole consumer INTO the package it depends on, or the sole target back
        # into the package that depends on it: both remove this edge, at different cost.
        moves = ([(consumers[0], e["to"])] if len(consumers) == 1 else []) + \
                ([(targets[0], e["from"])] if len(targets) == 1 else [])
        for cls, dst in moves:
            if (cls, dst) in seen:
                continue
            if accept is not None and not accept(cls, e["from"], e["to"]):
                continue
            eff = move_effect(class_graph, cls, dst)
            if not eff.get("ok"):
                continue
            if pair not in {tuple(x) for x in eff["removed"]} or eff["net"] >= 0:
                continue
            seen.add((cls, dst))
            out.append({"op": "moveClass", "type": cls, "toPackage": dst,
                        "edge": "%s -> %s" % pair,
                        "from_package": e["from"], "to_package": e["to"],
                        "classes_carrying_edge": e.get("classes", 1),
                        "predicted_removed": len(eff["removed"]),
                        "predicted_added": len(eff["added"]),
                        "predicted_net": eff["net"],
                        "predicted_added_edges": ["%s -> %s" % tuple(x) for x in eff["added"]],
                        # Stated before the run, so the check afterwards is a check.
                        "success_criterion":
                            "the bytecode edge %s -> %s no longer exists and at most %d new "
                            "package edges appear" % (pair[0], pair[1], len(eff["added"]))})
    out.sort(key=lambda c: (c["predicted_net"], c["predicted_added"]))
    return out[:limit]
