"""Static dependency-graph adapter.

Reads component dependency edges from CSV (from,to[,weight]), JSON
({"edges": [{"from": ..., "to": ...}]} or adjacency {"a": ["b", "c"]}),
or a minimal DOT subset ("a" -> "b";). Detects strongly connected components
(Tarjan) and emits one Cyclic Dependency smell per non-trivial SCC, so a plain
dependency graph is enough to drive the whole pipeline.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .base import (AdapterResult, RawEdge, RawSmell, ToolAdapter, pick,
                   read_csv_rows, register_adapter)

_DOT_EDGE_RE = re.compile(r'"?([\w.$\-/]+)"?\s*->\s*"?([\w.$\-/]+)"?')


def tarjan_sccs(edges: list[tuple[str, str]]) -> list[list[str]]:
    graph: dict[str, list[str]] = {}
    for frm, to in edges:
        graph.setdefault(frm, []).append(to)
        graph.setdefault(to, [])
    index_counter = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    sccs: list[list[str]] = []

    def strongconnect(node: str) -> None:
        # iterative Tarjan to avoid recursion limits on large graphs
        work = [(node, iter(graph[node]))]
        index[node] = lowlink[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack[node] = True
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = lowlink[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack[w] = True
                    work.append((w, iter(graph[w])))
                    advanced = True
                    break
                elif on_stack.get(w):
                    lowlink[v] = min(lowlink[v], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[v])
            if lowlink[v] == index[v]:
                scc = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    scc.append(w)
                    if w == v:
                        break
                sccs.append(scc)

    for node in graph:
        if node not in index:
            strongconnect(node)
    return sccs


@register_adapter
class StaticGraphAdapter(ToolAdapter):
    name = "static_graph"

    def parse_import(self, path: Path) -> AdapterResult:
        suffix = path.suffix.lower()
        if suffix in (".csv", ".tsv", ".txt"):
            edges = self._edges_from_csv(path)
        elif suffix == ".json":
            edges = self._edges_from_json(path)
        elif suffix in (".dot", ".gv"):
            edges = self._edges_from_dot(path)
        else:
            raise ValueError(f"StaticGraphAdapter cannot parse '{path.name}'")

        result = AdapterResult(edges=edges)
        pairs = [(e.from_component, e.to_component) for e in edges]
        self_loops = {frm for frm, to in pairs if frm == to}
        cycle_n = 0
        for scc in tarjan_sccs(pairs):
            members = sorted(scc)
            if not members:
                continue
            if len(members) < 2 and members[0] not in self_loops:
                continue
            cycle_n += 1
            result.smells.append(RawSmell(
                tool=self.name, tool_record_id=f"scc{cycle_n}",
                raw_source_file=path.name, smell_type_raw="Cyclic Dependency",
                affected_components=members,
                attributes={"cycle_size": len(members),
                            "detection": "tarjan_scc"}))
        return result

    def _edges_from_csv(self, path: Path) -> list[RawEdge]:
        rows = read_csv_rows(path)
        edges = []
        for row in rows:
            frm = pick(row, "from", "source", "src", "fromcomponent")
            to = pick(row, "to", "target", "dst", "tocomponent")
            if not frm or not to:
                continue
            weight_s = pick(row, "weight", "count", "strength")
            edges.append(RawEdge(tool=self.name, raw_source_file=path.name,
                                 from_component=frm, to_component=to,
                                 weight=float(weight_s) if weight_s else None))
        return edges

    def _edges_from_json(self, path: Path) -> list[RawEdge]:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        edges: list[RawEdge] = []
        if isinstance(data, dict) and "edges" in data:
            for e in data["edges"]:
                if isinstance(e, dict) and e.get("from") and e.get("to"):
                    edges.append(RawEdge(tool=self.name, raw_source_file=path.name,
                                         from_component=str(e["from"]),
                                         to_component=str(e["to"]),
                                         weight=e.get("weight")))
        elif isinstance(data, dict):  # adjacency map
            for frm, targets in data.items():
                for to in (targets if isinstance(targets, list) else [targets]):
                    edges.append(RawEdge(tool=self.name, raw_source_file=path.name,
                                         from_component=str(frm), to_component=str(to)))
        return edges

    def _edges_from_dot(self, path: Path) -> list[RawEdge]:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        return [RawEdge(tool=self.name, raw_source_file=path.name,
                        from_component=frm, to_component=to)
                for frm, to in _DOT_EDGE_RE.findall(text)]
