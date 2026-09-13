"""Eliminate specific dependency edges, cheapest first, verified in bytecode.

This replaces the target the whole pipeline used to aim at, and the reason is measured rather
than stylistic.

Arcan reports 802 Cyclic Dependency smells on pdfbox. The bytecode says five cycles, one
containing 51 of its 103 packages. Those 802 are one tangle counted per participating element.
Dissolving that component needs 167 package edges cut and 1177 classes abstracted; our best
single inversion abstracted four. It is not reachable, and chasing it produced three rankings
in a row that failed to generalise, because "how much did you peel off the blob" is dominated
by whichever move detaches a large subtree.

So stop claiming smell removal. Claim what can actually be delivered and checked:

    this specific package edge no longer exists, it cost N classes to remove,
    and the bytecode agrees.

That is a smaller claim and a true one. It is also what ArchUnit users already enforce in their
own builds, so the output lands in a form practitioners recognise.

Candidates come from the feedback arc set of a real component, ordered by the number of class
dependencies carrying each edge, because that count IS the work: every class creating the edge
has to be abstracted for the edge to fall.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..refactoring import spoon_plan
from ..refactoring.strategies import SourceFacts


def feedback_edges(cycle_data: Dict[str, Any], component_index: Optional[int] = None
                   ) -> List[Dict[str, Any]]:
    """Internal edges of one component, cheapest first.

    Defaults to the largest component, which is where the weight is: on pdfbox it holds 51 of
    103 packages. Cheapest first because an edge carried by one class is one inversion, and an
    edge carried by eighty is a rewrite nobody asked for.
    """
    cycles = cycle_data.get("cycles") or []
    edge_sets = cycle_data.get("cycleEdges") or []
    if not cycles or not edge_sets:
        return []
    idx = (component_index if component_index is not None
           else max(range(len(cycles)), key=lambda i: len(cycles[i])))
    if idx >= len(edge_sets):
        return []
    return sorted(edge_sets[idx], key=lambda e: (e.get("classes", 1), e["from"], e["to"]))


def cheap_edges(cycle_data: Dict[str, Any], max_classes: int = 3,
                component_index: Optional[int] = None) -> List[Dict[str, Any]]:
    """Edges within reach of the operations we actually have."""
    return [e for e in feedback_edges(cycle_data, component_index)
            if e.get("classes", 1) <= max_classes]


def crossing_types(facts: SourceFacts, from_pkg: str, to_pkg: str,
                   limit: int = 8) -> List[str]:
    """Types in `to_pkg` that `from_pkg` names — the ones creating the edge.

    Inverting the edge means abstracting every one of them. If the bytecode says the edge is
    carried by two classes and this finds five, trust the bytecode about the cost and treat the
    extra names as a source-level over-count: the text index cannot tell a mention in a comment
    from a real dependency.
    """
    consumer_files = {facts.file_for(f) for f in facts.classes_in(from_pkg)}
    consumer_files.discard(None)
    if not consumer_files:
        return []
    out = []
    for fqn in facts.classes_in(to_pkg):
        if facts.files_mentioning(fqn.rsplit(".", 1)[-1]) & consumer_files:
            out.append(fqn)
            if len(out) >= limit:
                break
    return out


def candidates_for_edge(facts: SourceFacts, edge: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One invertEdge plan aimed at removing a single named edge, with its cost attached.

    The consumer owns the abstraction, so the interface lands in `from` — the package that
    depends — and the implementations in `to` gain it. That direction is what removes the
    `from -> to` edge rather than relocating it.
    """
    src, dst = edge["from"], edge["to"]
    types = crossing_types(facts, src, dst)
    if not types:
        return None
    root_src = spoon_plan.package_root(facts, src)
    root_dst = spoon_plan.package_root(facts, dst)
    if root_src is None or root_src != root_dst:
        # The interface would land in one module and the implements clause compile in another,
        # which needs a build dependency that very likely runs the wrong way.
        return None
    edit = spoon_plan.Edit("invertEdge", types[0], src, types=types)
    if any(spoon_plan._why_not(spoon_plan.Edit("extractInterface", t, src), facts)
           for t in types):
        return None
    return {
        "edit": edit.as_dict(),
        "edge": f"{src} -> {dst}",
        "from_package": src,
        "to_package": dst,
        "classes_carrying_edge": edge.get("classes", 1),
        "types_to_abstract": types,
        # What success means here, stated before the run rather than inferred after it.
        "success_criterion": f"the bytecode edge {src} -> {dst} no longer exists",
    }


# Shapes that cannot be put behind an interface, in the order they actually occur. Measured on
# pdfbox's cheapest 18 edges, every one of which was refused: 7 were already interfaces, 4 had
# no instance method called, 4 were constructed directly, 2 were read as constants, 1 was a
# static helper.
_UNINVERTIBLE_HINTS = ("Exception", "Error", "Constants", "Util", "Utils", "Helper",
                       "Version", "Hex", "Name", "Names", "Mode", "Type", "Kind")


def invertibility(facts: SourceFacts, fqn: str) -> Tuple[int, str]:
    """A cheap source-level guess at whether a type can go behind an interface.

    Returns (score, why); higher is more promising. This never overrules the Spoon precheck,
    which decides legality with resolved types -- it exists so the expensive check is spent on
    candidates that have a chance, instead of on the eighteen that were refused in a row.

    Ranking by the number of classes carrying an edge was exactly backwards. An edge carried by
    ONE class is carried by a utility, a constant, an exception or an interface: cheap to name
    and impossible to abstract. What makes a type invertible is having behaviour to abstract --
    public instance methods someone calls.
    """
    text = facts.text_of(fqn) or ""
    simple = fqn.rsplit(".", 1)[-1]
    if not text:
        return -100, "no source"
    body = chr(10).join(ln for ln in text.splitlines() if not ln.strip().startswith("import "))
    if " interface " in body or body.lstrip().startswith("public interface"):
        return -100, "already an interface"
    if " enum " in body:
        return -100, "enum"
    if any(simple.endswith(h) for h in ("Exception", "Error")):
        return -90, "exception type"
    score, why = 0, []
    # Public instance methods are the whole substance of an interface.
    instance = sum(1 for ln in body.splitlines()
                   if ln.strip().startswith("public ") and "(" in ln
                   and " static " not in ln and " class " not in ln
                   and "=" not in ln.split("(")[0])
    score += instance * 10
    why.append(f"{instance} public instance methods")
    statics = body.count(" static ")
    score -= statics * 4
    if statics:
        why.append(f"{statics} statics")
    if any(simple.endswith(h) for h in _UNINVERTIBLE_HINTS):
        score -= 25
        why.append("utility-shaped name")
    return score, ", ".join(why)


def plan(facts: SourceFacts, cycle_data: Dict[str, Any], max_classes: int = 40,
         limit: int = 12, component_index: Optional[int] = None) -> List[Dict[str, Any]]:
    """Edge eliminations ordered by how invertible the edge's types are.

    NOT cheapest-first. Aiming at the cheapest edges produced 0 legal candidates out of 18,
    because an edge is cheap precisely when a single utility or constant class carries it. The
    invertible edges are the behaviour-rich ones, which sit further up the cost curve, so
    `max_classes` defaults high enough to reach them and the ordering does the work.
    """
    scored = []
    for e in feedback_edges(cycle_data, component_index):
        if e.get("classes", 1) > max_classes:
            continue
        c = candidates_for_edge(facts, e)
        if c is None:
            continue
        parts = [invertibility(facts, t) for t in c["types_to_abstract"]]
        # The group is only as invertible as its worst member: invertEdge abstracts every type
        # the consumer names, and one enum in the set sinks the edge.
        worst = min(p[0] for p in parts)
        c["invertibility"] = worst
        c["invertibility_why"] = "; ".join(
            f"{t.rsplit('.', 1)[-1]}: {w}" for t, (s, w) in zip(c["types_to_abstract"], parts))
        if worst <= -90:
            continue                      # provably pointless to precheck
        scored.append(c)
    scored.sort(key=lambda c: (-c["invertibility"], c["classes_carrying_edge"]))
    return scored[:limit]
