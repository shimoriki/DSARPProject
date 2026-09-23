"""The edge oracle must answer "is this edge gone", and must refuse to answer when blind.

cycleEdges alone could not answer it: when a component breaks up its edges leave that array
whether or not the dependency still exists.
"""
from dsarp.tools.archunit_runner import edge_map, edge_verdict


def _run(edges, cycles=()):
    return {"ok": True, "cycles": [list(c) for c in cycles],
            "edges": [{"from": f, "to": t, "classes": n} for f, t, n in edges]}


BEFORE = _run([("a", "b", 3), ("b", "a", 1)], cycles=[("a", "b")])


def test_edge_removed_with_no_new_cycle_is_clean():
    after = _run([("a", "b", 3)])
    v = edge_verdict(BEFORE, after, "b", "a")
    assert v["edge_removed"] and v["clean"] and v["cycles_after"] == 0
    assert v["classes_before"] == 1 and v["classes_after"] is None


def test_an_inversion_reports_the_edges_it_added():
    # b -> a is gone, but a -> api and b -> api are the cost of getting there.
    after = _run([("a", "b", 3), ("a", "api", 1), ("b", "api", 1)])
    v = edge_verdict(BEFORE, after, "b", "a")
    assert v["edges_added"] == ["a -> api", "b -> api"] and v["clean"]


def test_a_new_cycle_is_not_a_clean_removal():
    after = _run([("a", "b", 3), ("b", "c", 1), ("c", "b", 1)], cycles=[("b", "c")])
    v = edge_verdict(BEFORE, after, "b", "a")
    assert v["edge_removed"] and not v["clean"]
    assert v["cycles_introduced"] == [["b", "c"]]


def test_a_failed_run_is_unanswerable_not_good_news():
    assert edge_verdict(BEFORE, {"ok": False, "why": "no classes"}, "b", "a") == {
        "answerable": False, "why": "no classes"}
    assert edge_map({"ok": False}) == {}


class _Facts:
    """Just enough SourceFacts for bytecode_types: which FQNs have source here."""
    def __init__(self, known):
        self.known = set(known)

    def file_for(self, fqn):
        return "x.java" if fqn in self.known else None


def test_carriers_name_the_types_an_inversion_must_abstract():
    from dsarp.agents.edge_elimination import bytecode_types
    edge = {"carriers": ["a.Consumer -> b.Target", "a.Other -> b.Target",
                         "a.Consumer -> b.Outer$Inner", "a.Consumer -> b.Generated"]}
    # deduplicated, nested types reduced to their file, and Generated has no source here
    assert bytecode_types(_Facts({"b.Target", "b.Outer"}), edge) == ["b.Target", "b.Outer"]


def test_an_edge_made_only_of_calls_has_nothing_to_retarget():
    from dsarp.agents.edge_elimination import declares_target
    assert declares_target({"kinds": {"Method calls method": 16}}) is False
    assert declares_target({"kinds": {"Method calls method": 9,
                                      "Field has type": 1}}) is True
    # snapshots taken before kinds were recorded must not read as "no declarations"
    assert declares_target({"carriers": ["a.A -> b.B"]}) is None


def test_the_component_join_carries_every_detail_the_predictors_need():
    # cycleEdges holds weights only; the detail lives in the flat edges array, and a join
    # that drops `kinds` makes "no declarations" read as "unknown" -- which passes.
    from dsarp.agents.edge_elimination import feedback_edges
    snap = {"cycles": [["a", "b"]], "cycleEdges": [[{"from": "a", "to": "b", "classes": 3}]],
            "edges": [{"from": "a", "to": "b", "classes": 3,
                       "carriers": ["a.C -> b.T"], "constructs": [],
                       "kinds": {"Method calls method": 3}}]}
    e = feedback_edges(snap)[0]
    assert e["carriers"] and e["kinds"] == {"Method calls method": 3}
