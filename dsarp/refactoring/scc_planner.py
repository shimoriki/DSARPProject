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

from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

Move = Tuple[str, str]


def _top(cls: str) -> str:
    return cls.split("$")[0]


def _pkg(cls: str) -> str:
    return cls.rsplit(".", 1)[0]


def top_level_edges(edges: Iterable) -> Set[Tuple[str, str]]:
    """Class edges with nested classes folded into their owner: they move together."""
    return {(_top(a), _top(b)) for a, b in edges if _top(a) != _top(b)}


def package_edges(edges: Set[Tuple[str, str]], moved: Dict[str, str],
                  inverted: Iterable[Tuple[str, str]] = (),
                  sig: Optional[Callable[[str], Set[str]]] = None) -> Set[Tuple[str, str]]:
    """Package edges after `moved`, and after each (consumer_pkg, impl) inversion.

    An inversion drops the consumer's edges to `impl`, adds `impl -> consumer` for the
    implements clause, and keeps `consumer -> T` for each type T the interface's signatures name.
    """
    inv = set(inverted)
    where = lambda c: moved.get(c) or _pkg(c)
    out = set()
    for a, b in edges:
        pa, pb = where(a), where(b)
        if pa != pb and (pa, b) not in inv:
            out.add((pa, pb))
    for consumer, impl in inv:
        for p, q in [(where(impl), consumer)] + [(consumer, where(t)) for t in (sig(impl) if sig else ())]:
            if p != q:
                out.add((p, q))
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
         width: int = 20, depth: int = 4,
         inversions: Optional[List[Tuple[str, str]]] = None,
         blocked: Optional[Callable[[str, str, Dict[str, str]], Optional[str]]] = None,
         sig: Optional[Callable[[str], Set[str]]] = None) -> Dict[str, Any]:
    """Beam search for the smallest operation set that shrinks `comp` most.

    A state is a set of moves, plus with `inversions` a set of (consumer_pkg, impl) pairs to
    put behind a consumer-owned interface. Lower is better on (packages of comp still cycling,
    packages newly pulled into a cycle, operations used). A plan that pulls an outside package
    into any cycle is dropped: across 130 plans from the package-level planners, that was the
    failure that made a move look good while the graph got worse. Every inversion in a state is
    re-judged by `blocked` against that state's moves, since a move can bring a blocker in.
    """
    base = set().union(*components(package_edges(edges, {})))
    Op = Tuple[str, str, str]

    def split(state: FrozenSet[Op]) -> Tuple[Dict[str, str], List[Tuple[str, str]]]:
        return ({a: b for k, a, b in state if k == "move"},
                sorted((a, b) for k, a, b in state if k == "invert"))

    def score(state: FrozenSet[Op]) -> Optional[Tuple[int, int, int]]:
        moved, inv = split(state)
        if blocked and any(blocked(p, i, moved) for p, i in inv):
            return None
        now = components(package_edges(edges, moved, inv, sig))
        cycling = set().union(*now) if now else set()
        return (len(cycling & comp), len(cycling - base), len(state))

    start: FrozenSet[Op] = frozenset()
    best = (score(start), start)
    beam = [best]
    moves = _candidates(edges, comp, accept)
    ops: List[Op] = [("move", c, d) for c, d in moves] + \
        [("invert", p, i) for p, i in (inversions or [])]
    for _ in range(depth):
        seen, grown = set(), []
        for _, state in beam:
            moved_now = {a for k, a, _ in state if k == "move"}
            for op in ops:
                if op in state or (op[0] == "move" and op[1] in moved_now):
                    continue
                next_state = state | {op}
                if next_state in seen:
                    continue
                seen.add(next_state)
                s = score(next_state)
                if s is not None and s[1] == 0:
                    grown.append((s, next_state))
        if not grown:
            break
        grown.sort(key=lambda x: (x[0], sorted(x[1])))
        beam = grown[:width]
        if beam[0][0] < best[0]:
            best = beam[0]
        if best[0][0] == 0:
            break
    (left, _, _), state = best
    moved, inv = split(state)
    out = {"component": sorted(comp), "size": len(comp), "predicted_left": left,
           "dissolves": left == 0, "moves": sorted(moved.items()),
           "candidates": len(moves)}
    if inversions is not None:
        out["inversions"] = [list(x) for x in inv]
    return out


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
