"""The planner proposes only moves it can show will help, and says by how much."""
from dsarp.refactoring.move_planner import in_cycle_edges, plan_moves

SNAP = {
    "cycles": [["a", "b"]],
    "edges": [
        # a -> b is carried by one class; b -> a by two, so only a -> b has a single carrier.
        {"from": "a", "to": "b", "classes": 1, "carriers": ["a.Mover -> b.Target"]},
        {"from": "b", "to": "a", "classes": 2,
         "carriers": ["b.One -> a.Keep", "b.Two -> a.Keep"]},
        # outside any cycle: not worth attacking even though it is single-carrier
        {"from": "c", "to": "d", "classes": 1, "carriers": ["c.Lone -> d.Thing"]},
    ],
}
GRAPH = {"ok": True, "edges": [("a.Mover", "b.Target"), ("b.One", "a.Keep"),
                               ("b.Two", "a.Keep"), ("c.Lone", "d.Thing")]}


def test_only_edges_inside_a_cycle_are_attacked():
    assert in_cycle_edges(SNAP) == {("a", "b"), ("b", "a")}
    assert all(p["edge"] != "c -> d" for p in plan_moves(SNAP, GRAPH))


def test_a_plan_states_what_it_will_remove_and_what_it_will_cost():
    p = plan_moves(SNAP, GRAPH)[0]
    assert (p["type"], p["toPackage"]) == ("a.Mover", "b")
    assert p["predicted_removed"] == 1 and p["predicted_added"] == 0
    assert "a -> b no longer exists" in p["success_criterion"]


def test_a_move_that_would_leave_the_graph_no_better_is_not_proposed():
    # Mover also uses e.Thing, and a.Other keeps a -> e alive after Mover leaves. So the move
    # trades a -> b for a brand new b -> e: net 0, and not worth proposing.
    graph = {"ok": True, "edges": GRAPH["edges"] + [("a.Mover", "e.Thing"),
                                                    ("a.Other", "e.Thing")]}
    assert not [p for p in plan_moves(SNAP, graph) if p["type"] == "a.Mover"]


def test_the_caller_can_refuse_what_it_cannot_apply():
    assert plan_moves(SNAP, GRAPH, accept=lambda cls, frm, to: False) == []
