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
    assert not [p for p in plan_moves(SNAP, graph, objective="edges")
                if p["type"] == "a.Mover"]


def test_the_caller_can_refuse_what_it_cannot_apply():
    assert plan_moves(SNAP, GRAPH, accept=lambda cls, frm, to: False) == []


# a.Mover is the sole carrier of a -> b, and it also uses c.Helper. Moving it to b breaks the
# a/b cycle and adds b -> c: MORE edges, FEWER packages in a cycle. This is the shape of the
# expert refactoring of Commons Compress, which added a package edge (108 -> 109) and lifted ten
# packages out of the big cycle (28 -> 18).
LIFT_SNAP = {"cycles": [["a", "b"]], "edges": [
    {"from": "a", "to": "b", "classes": 1, "carriers": ["a.Mover -> b.Target"]},
    {"from": "b", "to": "a", "classes": 1, "carriers": ["b.Target -> a.Stay"]},
]}
LIFT_GRAPH = {"ok": True, "edges": [
    ("a.Mover", "b.Target"),     # the only a -> b
    ("b.Target", "a.Stay"),      # b -> a closes the cycle
    ("a.Mover", "c.Helper"),     # moving Mover to b creates b -> c
    ("a.Stay", "c.Helper"),      # ... and a -> c survives, so the edge is genuinely added
]}


def test_the_edge_objective_refuses_a_move_that_takes_packages_out_of_a_cycle():
    plans = plan_moves(LIFT_SNAP, LIFT_GRAPH, objective="edges")
    assert not [p for p in plans if p["type"] == "a.Mover"], \
        "ranking on edge count accepted a net-positive move"


def test_the_participation_objective_accepts_it():
    plans = plan_moves(LIFT_SNAP, LIFT_GRAPH, objective="participation")
    mover = next((p for p in plans if p["type"] == "a.Mover"), None)
    assert mover is not None, "the move that empties the cycle was refused"
    assert mover["predicted_net"] >= 0, "this test only means something if edges do not fall"
    assert mover["predicted_participation_delta"] < 0
    assert mover["objective"] == "participation"


def test_participation_is_the_default_objective():
    assert plan_moves(LIFT_SNAP, LIFT_GRAPH)[0]["objective"] == "participation"


def test_a_move_that_drags_another_package_into_the_cycle_is_refused():
    """118 of 130 plans from the package-level planners raised participation; none lowered it.

    a and b form a cycle; d sits outside it. Moving a.M into d breaks a -> b and closes a NEW
    ring a -> d -> b -> a, so the same number of edges now traps three packages instead of two.
    Edge counting scores this as neutral and would let it through.
    """
    snap = {"cycles": [["a", "b"]], "edges": [
        {"from": "a", "to": "b", "classes": 1, "carriers": ["a.M -> b.T"]}]}
    graph = {"ok": True, "edges": [
        ("a.M", "b.T"),     # the only a -> b
        ("b.T", "a.S"),     # closes the a/b cycle
        ("a.M", "d.W"),     # moving a.M to d internalises this
        ("a.S", "d.W"),     # ... and keeps a -> d alive
    ]}
    to_d = [p for p in plan_moves(snap, graph, objective="participation")
            if p["type"] == "a.M" and p["toPackage"] == "d"]
    assert not to_d, "a move that enlarged the cycle was proposed"
    # Both objectives refuse this one, for different reasons: participation because the cycle
    # grew, edges because the total did not fall. The case where they DISAGREE is the pair of
    # tests above, where edges refuses a move that empties a cycle at the cost of one edge.
