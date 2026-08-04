"""Loop 5 — dependency graph construction + metrics (NetworkX).

Builds a directed package/class graph from edges and computes the metrics the
ranker and candidate generator need: cycles, SCCs, fan-in/out, centrality.
Also produces a compact graph_summary (token layer) rather than dumping the graph.
"""
from __future__ import annotations

from typing import Any, Dict, List

import networkx as nx

from ..schemas import DependencyGraph, GraphEdge, GraphNode
from ..util import evidence_id, sha256_of


class DependencyGraphBuilder:
    def build(self, edges: List[Dict[str, Any]], kind: str = "package") -> DependencyGraph:
        g = nx.DiGraph()
        model_edges: List[GraphEdge] = []
        for e in edges:
            src, tgt = e["source"], e["target"]
            w = float(e.get("weight", 1.0))
            eid = e.get("evidence_id") or evidence_id("EDGE", src, tgt)
            g.add_edge(src, tgt, weight=w)
            model_edges.append(GraphEdge(source=src, target=tgt, weight=w,
                                         kind=e.get("kind", "depends_on"), evidence_id=eid))
        nodes = self._node_metrics(g, kind)
        return DependencyGraph(nodes=nodes, edges=model_edges, graph_metrics=self._graph_metrics(g))

    def _node_metrics(self, g: nx.DiGraph, kind: str) -> List[GraphNode]:
        centrality = nx.betweenness_centrality(g) if g.number_of_nodes() else {}
        out: List[GraphNode] = []
        for n in g.nodes():
            fi, fo = g.in_degree(n), g.out_degree(n)
            # Martin's instability I = Ce / (Ca + Ce) = fan_out / (fan_in + fan_out)
            instability = round(fo / (fi + fo), 4) if (fi + fo) else 0.0
            out.append(GraphNode(id=n, kind=kind, metrics={
                "fan_in": fi,
                "fan_out": fo,
                "instability": instability,
                "betweenness": round(centrality.get(n, 0.0), 4),
            }))
        return out

    def _graph_metrics(self, g: nx.DiGraph, max_cycles: int = 2000) -> Dict[str, Any]:
        # simple_cycles is a generator; enumerating ALL cycles can be exponential on
        # large cyclic package graphs, so we bound it (islice) to stay laptop-safe.
        import itertools
        try:
            cycles = list(itertools.islice(nx.simple_cycles(g), max_cycles))
        except Exception:
            cycles = []
        sccs = [list(c) for c in nx.strongly_connected_components(g) if len(c) > 1]
        return {
            "node_count": g.number_of_nodes(),
            "edge_count": g.number_of_edges(),
            "cycle_count": len(cycles),
            "cycles": cycles[:50],
            "scc_count": len(sccs),
            "sccs": sccs[:50],
        }

    @staticmethod
    def edges_hash(edges: List[Dict[str, Any]], revision: str = "") -> str:
        """Stable hash for graph caching by revision + edge content."""
        norm = sorted((str(e.get("source")), str(e.get("target")), float(e.get("weight", 1.0)))
                      for e in edges)
        return sha256_of([revision, norm])

    @staticmethod
    def to_networkx(dg: DependencyGraph) -> nx.DiGraph:
        g = nx.DiGraph()
        for n in dg.nodes:
            g.add_node(n.id, **n.metrics)
        for e in dg.edges:
            g.add_edge(e.source, e.target, weight=e.weight)
        return g

    @staticmethod
    def slice_around(dg: DependencyGraph, components: List[str], hops: int = 1) -> Dict[str, Any]:
        """Graph slice: affected components + neighbours within `hops`.

        This is what the UI renders and (a compact form of) what feeds the LLM —
        never the full graph (token policy).
        """
        g = DependencyGraphBuilder.to_networkx(dg)
        keep: set = set(c for c in components if c in g)
        frontier = set(keep)
        for _ in range(max(0, hops)):
            nxt: set = set()
            for n in frontier:
                nxt.update(g.successors(n))
                nxt.update(g.predecessors(n))
            keep.update(nxt)
            frontier = nxt
        sub = g.subgraph(keep)
        metric_by_id = {n.id: n.metrics for n in dg.nodes}
        return {
            "focus": [c for c in components if c in g],
            "nodes": [{"id": n, "metrics": metric_by_id.get(n, {})} for n in sub.nodes()],
            "edges": [{"source": u, "target": v} for u, v in sub.edges()],
            "node_count": sub.number_of_nodes(), "edge_count": sub.number_of_edges(),
        }

    @staticmethod
    def summary(dg: DependencyGraph, top_k: int = 10) -> Dict[str, Any]:
        """Compact graph_summary.json content — no full graph dump."""
        by_fanio = sorted(dg.nodes, key=lambda n: n.metrics.get("fan_in", 0)
                          + n.metrics.get("fan_out", 0), reverse=True)
        return {
            "node_count": dg.graph_metrics.get("node_count", 0),
            "edge_count": dg.graph_metrics.get("edge_count", 0),
            "cycle_count": dg.graph_metrics.get("cycle_count", 0),
            "scc_count": dg.graph_metrics.get("scc_count", 0),
            "central_components": [n.id for n in by_fanio[:top_k]],
        }
