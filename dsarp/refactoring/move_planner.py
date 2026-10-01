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
               limit: int = 20, objective: str = "participation") -> List[Dict[str, Any]]:
    """Moves worth making, best first, judged on how many packages stay inside a cycle.

    Only edges carried by a single class on one side are considered: with two carriers the
    move is a package merge in disguise, and the caller has no operation for it.

    `accept(class_fqn, from_package, to_package)` rejects what this repository cannot apply --
    a class with no source here, or a destination in a different Maven module, where the file
    would land where the build cannot see it.

    `objective` decides what "worth making" means, and the default changed on evidence:

      "participation" -- accept a move that takes packages out of a cycle, even if the edge
          count rises. This is what the experts did. Arcelli Fontana's hand-refactored
          noDependency tree for Commons Compress ADDED a package edge (108 -> 109) and lifted
          ten packages out of the big cycle (28 -> 18, and the surviving cycle is a strict
          subset of the old one). Ranking on edge count refused that change outright.
      "edges" -- the original rule, net package edges only. Kept because every verified result
          in this repository so far was produced under it, so it has to stay reproducible.

    Neither objective is a proxy for "the smell is gone". No cycle has ever been dissolved here,
    nor in either of the two hand-refactored trees, so both measure improvement rather than cure.
    """
    before_edges = package_edges_after(class_graph, [], "__none__")
    before_part = participation(before_edges) if before_edges is not None else None
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
            if pair not in {tuple(x) for x in eff["removed"]}:
                continue
            d_part = None
            if before_part is not None:
                after = package_edges_after(class_graph, cls, dst)
                d_part = participation(after)["participation"] - before_part["participation"]
            if objective == "participation" and d_part is not None:
                # Fewer packages in cycles, or the same number for fewer edges. A move that
                # pushes another package into a cycle is refused however many edges it removes:
                # across 130 plans from the three package-level planners, 118 raised
                # participation, and splitting raised it while never once lowering it.
                if not (d_part < 0 or (d_part == 0 and eff["net"] < 0)):
                    continue
            elif eff["net"] >= 0:
                continue
            seen.add((cls, dst))
            out.append({"op": "moveClass", "type": cls, "toPackage": dst,
                        "edge": "%s -> %s" % pair,
                        "from_package": e["from"], "to_package": e["to"],
                        "classes_carrying_edge": e.get("classes", 1),
                        # Both sides of the edge, so a caller comparing operations can aim a
                        # dependency inversion at the same edge without re-deriving them.
                        "consumers": consumers, "targets": targets,
                        "predicted_removed": len(eff["removed"]),
                        "predicted_added": len(eff["added"]),
                        "predicted_net": eff["net"],
                        "predicted_participation_delta": d_part,
                        "objective": objective,
                        "predicted_added_edges": ["%s -> %s" % tuple(x) for x in eff["added"]],
                        # Stated before the run, so the check afterwards is a check.
                        "success_criterion":
                            "the bytecode edge %s -> %s no longer exists and at most %d new "
                            "package edges appear" % (pair[0], pair[1], len(eff["added"]))})
    if objective == "participation":
        out.sort(key=lambda c: (c.get("predicted_participation_delta") if
                                c.get("predicted_participation_delta") is not None else 0,
                                c["predicted_net"], c["predicted_added"]))
    else:
        out.sort(key=lambda c: (c["predicted_net"], c["predicted_added"]))
    return out[:limit]


def package_edges_after(class_graph: Dict[str, Any], group, to_package: str):
    """The package edge set that results from relabelling `group` into `to_package`.

    The same relabelling move_effect uses, returned whole rather than as a diff, so a caller can
    ask structural questions of the result -- which cycles survive, how many packages still
    participate in one -- without compiling anything.
    """
    if not class_graph.get("ok"):
        return None
    members = {group} if isinstance(group, str) else set(group)
    pkg = lambda c: c.rsplit(".", 1)[0]
    moved = lambda c: (to_package if any(c == m or c.startswith(m + "$") for m in members)
                       else pkg(c))
    out = set()
    for a, b in class_graph["edges"]:
        if moved(a) != moved(b):
            out.add((moved(a), moved(b)))
    return out


def participation(edges) -> Dict[str, Any]:
    """Packages that sit in a cycle, and the size of each cycle.

    This is the quantity Arcan's Cyclic Dependency count approximates and the one the expert
    refactoring of Commons Compress actually moved: 28 packages in cycles before, 18 after, while
    the edge count went UP by one. A planner that ranks on edge count alone cannot see that, and
    would have refused the change.
    """
    import networkx as nx
    g = nx.DiGraph()
    g.add_edges_from(edges or [])
    comps = [c for c in nx.strongly_connected_components(g) if len(c) > 1]
    sizes = sorted((len(c) for c in comps), reverse=True)
    return {"cycles": len(comps), "participation": sum(sizes), "sizes": sizes,
            "largest": sizes[0] if sizes else 0,
            "components": [sorted(c) for c in comps]}
