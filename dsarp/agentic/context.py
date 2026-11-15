"""The planner's view of one package cycle, and the prompt built from it."""
from __future__ import annotations

import json
from typing import Any, Dict, Set, Tuple

from ..refactoring.scc_planner import _pkg, top_level_edges

CATALOGUE = """Operations you may use (no others):
- moveClass: move one top-level class to another existing package.
  {"op": "moveClass", "class": "<fully.qualified.Class>", "to": "<existing.package>"}
- invertEdge: the consumer package gets an interface that the implementation class implements,
  so the consumer's dependency on that class points the other way.
  {"op": "invertEdge", "consumer": "<package>", "impl": "<fully.qualified.Class>"}"""

FORMAT = """Answer with one JSON object and nothing else:
{"operations": [ ... ], "rationale": "<one sentence>"}"""

RULES = """Rules (a plan that breaks one is rejected and you get the reason):
- Name classes by top-level fully qualified name only; no nested (A$B) or simple names.
- The destination must be a package that already exists.
- Do not move a class into another Maven module.
- Do not move a public class into an internal or impl package.
- A plan that pulls any package outside this cycle into a cycle is rejected.
- Goal: no package of this cycle is left in any cycle, with as few operations as possible."""


def build_context(edges: Set[Tuple[str, str]], comp: Set[str], max_carriers: int = 60) -> Dict[str, Any]:
    by_pair: Dict[Tuple[str, str], list] = {}
    for a, b in top_level_edges(edges):
        pa, pb = _pkg(a), _pkg(b)
        if pa != pb and pa in comp and pb in comp:
            by_pair.setdefault((pa, pb), []).append([a, b])
    carriers = [c for _, cs in sorted(by_pair.items(), key=lambda kv: (len(kv[1]), kv[0]))
                for c in sorted(cs)][:max_carriers]
    classes = sorted({c for a, b in top_level_edges(edges) for c in (a, b) if _pkg(c) in comp})
    return {"packages": sorted(comp),
            "package_edges": [[a, b, len(cs)] for (a, b), cs in sorted(by_pair.items())],
            "carriers": carriers, "classes": classes}


def render(ctx: Dict[str, Any], feedback: str = "") -> str:
    parts = ["You plan architectural refactorings that remove one Java package cycle.",
             CATALOGUE, FORMAT, RULES,
             "Packages in the cycle:\n" + "\n".join(ctx["packages"]),
             "Package edges [from, to, class edges]:\n" + json.dumps(ctx["package_edges"]),
             "Class edges carrying them [from, to], cheapest package edge first:\n"
             + "\n".join("%s -> %s" % (a, b) for a, b in ctx["carriers"]),
             "Classes in the cycle's packages:\n" + "\n".join(ctx["classes"])]
    if feedback:
        parts.append("Your previous plan was checked:\n" + feedback)
    return "\n\n".join(parts) + "\n"
