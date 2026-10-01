"""Participation is the quantity the expert refactoring moved; the planner must predict it.

Commons Compress's noDependency version went from 28 packages in cycles to 18 while its edge
count went UP by one. A planner ranking on edge count alone would have refused that change, and
did refuse it: move_planner only proposes predicted_net < 0.
"""
from dsarp.refactoring.move_planner import package_edges_after, participation

# a.X -> b.Y -> a.Z -> c.W -> a.X : packages a, b, c form one cycle
GRAPH = {"ok": True, "edges": [("a.X", "b.Y"), ("b.Y", "a.Z"), ("a.Z", "c.W"), ("c.W", "a.X")]}


def test_participation_counts_packages_in_cycles_not_edges():
    p = participation({("a", "b"), ("b", "a"), ("a", "c"), ("c", "a")})
    assert p["cycles"] == 1 and p["participation"] == 3 and p["largest"] == 3


def test_a_package_outside_any_cycle_does_not_participate():
    p = participation({("a", "b"), ("b", "a"), ("a", "leaf")})
    assert p["participation"] == 2 and p["components"] == [["a", "b"]]


def test_the_after_graph_is_derived_by_relabelling_one_class():
    after = package_edges_after(GRAPH, "a.X", "d")
    assert ("c", "d") in after and ("d", "b") in after
    assert ("c", "a") not in after, "the moved class still answers to its old package"


def test_a_split_can_lengthen_the_cycle_it_was_meant_to_break():
    # moving a.X out inserts d into the ring instead of breaking it: 3 packages become 4
    before = participation({("a", "b"), ("b", "a"), ("a", "c"), ("c", "a")})
    after = participation(package_edges_after(GRAPH, "a.X", "d"))
    assert after["participation"] > before["participation"]


def test_a_failed_graph_predicts_nothing_rather_than_an_empty_graph():
    assert package_edges_after({"ok": False}, "a.X", "d") is None
