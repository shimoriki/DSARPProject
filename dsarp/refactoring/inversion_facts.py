"""What the SCC planner needs to put a consumer-owned interface between two packages.

An inversion of `impl` from `consumer_pkg` extracts an interface into the consumer and makes
`impl` implement it, so the consumer's declarations stop naming `impl`. It removes the edge only
when nothing else holds it up, and some of what holds it up moves with the plan: a class that
builds `impl` with `new` keeps the edge, and moving that class out of the consumer unblocks the
inversion. So blockers are judged per planner state, against packages after its moves.

Static, field and subclass use are not read here. The Spoon dry-run refuses those, and it stays
the authority: this only keeps the beam from spending itself on pairs that cannot work.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ..agents.edge_elimination import declares_target, invertibility
from . import spoon_plan

_TYPE = re.compile(r"\b([A-Z]\w*)\b")
_IMPORT = re.compile(r"^\s*import\s+([\w.]+)\s*;", re.M)


def _top(cls: str) -> str:
    return cls.split("$")[0]


def _pkg(cls: str) -> str:
    return cls.rsplit(".", 1)[0]


class InversionFacts:
    def __init__(self, snapshot: Dict[str, Any], facts):
        self.facts = facts
        self.edges = {(e["from"], e["to"]): e for e in snapshot.get("edges") or []}
        # impl -> classes that construct it, from the oracle's own record of `new` sites.
        self.builders: Dict[str, Set[str]] = {}
        for e in self.edges.values():
            for pair in e.get("constructs") or []:
                if " -> " in pair:
                    a, b = pair.split(" -> ")
                    self.builders.setdefault(_top(b), set()).add(_top(a))
        self._sig: Dict[str, Set[str]] = {}

    def candidates(self, class_edges, comp: Set[str]) -> List[Tuple[str, str]]:
        """(consumer_pkg, impl) for each in-component class edge, impl being top-level."""
        return sorted({(_pkg(a), b) for a, b in class_edges
                       if _pkg(a) in comp and _pkg(b) in comp and _pkg(a) != _pkg(b)})

    def blocked(self, consumer_pkg: str, impl: str, moved: Dict[str, str]) -> Optional[str]:
        """Why this inversion cannot remove the edge in the state `moved`, or None."""
        if not self.facts.file_for(impl):
            return "no source"
        score, why = invertibility(self.facts, impl)
        if score <= -90:
            return why
        root = spoon_plan.source_root_of(self.facts, impl)
        if root is None or root != spoon_plan.package_root(self.facts, consumer_pkg):
            return "consumer and implementation in different source roots"
        edge = self.edges.get((consumer_pkg, _pkg(impl)))
        # Judged on the baseline edge only: after moves the snapshot no longer describes it.
        if edge is not None and declares_target(edge) is False:
            return "the consumer declares nothing of that type"
        builder = next((b for b in sorted(self.builders.get(impl, ()))
                        if (moved.get(b) or _pkg(b)) == consumer_pkg), None)
        return "constructed by %s" % builder if builder else None

    def signature_types(self, impl: str) -> Set[str]:
        """Repository types named in impl's public instance method signatures.

        The interface carries these signatures, so each named type is an edge from the consumer
        that survives the inversion (Jackrabbit's getSessionImpl). Conservative: every public
        instance method counts, not only those the consumer calls.
        """
        if impl in self._sig:
            return self._sig[impl]
        text = self.facts.text_of(impl) or ""
        imports = {i.rsplit(".", 1)[1]: i for i in _IMPORT.findall(text)}
        own = _pkg(impl)
        out: Set[str] = set()
        for line in text.splitlines():
            s = line.strip()
            head = s.split("(")[0]
            if not s.startswith("public ") or "(" not in s or " static " in s or " class " in s \
                    or "=" in head or head.split()[-1] == impl.rsplit(".", 1)[1]:   # constructor
                continue
            for name in _TYPE.findall(s.split(")")[0]):
                fqn = imports.get(name) or "%s.%s" % (own, name)
                if fqn != impl and self.facts.file_for(fqn):
                    out.add(fqn)
        self._sig[impl] = out
        return out
