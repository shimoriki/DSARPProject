"""Plans that take a whole package cycle apart, computed before anything is applied.

`move_planner` asks which single class removes one edge. That cannot dissolve a cycle: on
log4j2, moving JsonTemplateLayout alone left the json/resolver cycle standing, because classes
in another module still used it from the old package. Moving it with JsonTemplateLayoutDefaults
took the cycle apart, as this arithmetic predicted exactly.

So the search is over SETS of moves within one strongly connected component, smallest
component first. The score is arithmetic on the class graph, not a fitted model: five of those
failed on held-out repositories (docs/negative-results.md).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

Move = Tuple[str, str]


def _top(cls: str) -> str:
    return cls.split("$")[0]


def _pkg(cls: str) -> str:
    return cls.rsplit(".", 1)[0]


def top_level_edges(edges: Iterable) -> Set[Tuple[str, str]]:
    """Class edges with nested classes folded into their owner: they move together."""
    return {(_top(a), _top(b)) for a, b in edges if _top(a) != _top(b)}


def package_edges(edges: Set[Tuple[str, str]], moved: Dict[str, str]) -> Set[Tuple[str, str]]:
    out = set()
    for a, b in edges:
        pa, pb = moved.get(a) or _pkg(a), moved.get(b) or _pkg(b)
        if pa != pb:
            out.add((pa, pb))
    return out


def components(package_graph: Set[Tuple[str, str]]) -> List[Set[str]]:
    """Strongly connected package groups of two or more, smallest first."""
    import networkx as nx
    g = nx.DiGraph()
    g.add_edges_from(package_graph)
    return sorted((c for c in nx.strongly_connected_components(g) if len(c) > 1), key=len)


def _candidates(edges: Set[Tuple[str, str]], comp: Set[str],
                accept: Optional[Callable[[str, str], bool]]) -> List[Move]:
    """Classes with a tie across the component, to each component package they touch."""
    touches: Dict[str, Set[str]] = {}
    for a, b in edges:
        pa, pb = _pkg(a), _pkg(b)
        if pa in comp and pb in comp and pa != pb:
            touches.setdefault(a, set()).add(pb)
            touches.setdefault(b, set()).add(pa)
    moves = [(c, d) for c, dests in touches.items() for d in sorted(dests) if d != _pkg(c)]
    return sorted(m for m in moves if accept is None or accept(*m))


def plan(edges: Set[Tuple[str, str]], comp: Set[str],
         accept: Optional[Callable[[str, str], bool]] = None,
         width: int = 20, depth: int = 4) -> Dict[str, Any]:
    """Beam search for the smallest move set that shrinks `comp` most.

    A state is a set of moves. Lower is better on (packages of comp still cycling, packages
    newly pulled into a cycle, moves used). A plan that pulls an outside package into any
    cycle is dropped: across 130 plans from the package-level planners, that was the failure
    that made a move look good while the graph got worse.
    """
    base = set().union(*components(package_edges(edges, {})))

    def score(moved: Dict[str, str]) -> Tuple[int, int, int]:
        now = components(package_edges(edges, moved))
        cycling = set().union(*now) if now else set()
        return (len(cycling & comp), len(cycling - base), len(moved))

    start: Dict[str, str] = {}
    best = (score(start), start)
    beam = [best]
    moves = _candidates(edges, comp, accept)
    for _ in range(depth):
        seen, grown = set(), []
        for _, state in beam:
            for cls, dest in moves:
                if cls in state:
                    continue
                next_state = {**state, cls: dest}
                key = tuple(sorted(next_state.items()))
                if key in seen:
                    continue
                seen.add(key)
                s = score(next_state)
                if s[1] == 0:
                    grown.append((s, next_state))
        if not grown:
            break
        grown.sort(key=lambda x: (x[0], sorted(x[1].items())))
        beam = grown[:width]
        if beam[0][0] < best[0]:
            best = beam[0]
        if best[0][0] == 0:
            break
    (left, _, _), moved = best
    return {"component": sorted(comp), "size": len(comp), "predicted_left": left,
            "dissolves": left == 0, "moves": sorted(moved.items()),
            "candidates": len(moves)}


def level(comp: Set[str], before_cycles: List[Set[str]], after_cycles: List[Set[str]],
          edges_removed: int, tests_state: str, arcan_target_gone: Optional[bool]) -> str:
    """The evidence level one result has earned, in docs/ARCHITECTURE_SMELL_REDESIGN.md terms.

    Tests that did not pass cap everything at 2: a structural result on unverified behaviour
    is a patch, not a success. 4c also needs the detector to agree, since it is the oracle.
    """
    if tests_state != "PASS":
        return "2"
    new = [c for c in after_cycles if not any(c <= b for b in before_cycles)]
    if new:
        return "3"
    still = [c for c in after_cycles if c & comp]
    if not still:
        return "4c" if arcan_target_gone else "4b"
    if any(c < comp for c in still):
        return "4b"
    return "4a" if edges_removed else "3"
