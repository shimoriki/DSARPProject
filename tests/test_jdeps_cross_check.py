"""jdeps is the second reading of the same bytecode; it must agree about our packages only.

ArchUnit was once silently blind on newer class files and still reported success, so the
oracle's verdicts now rest on two independent readers rather than one.
"""
from dsarp.tools.jdeps_runner import cross_check, parse

SAMPLE = """classes -> java.base
classes -> not found
   com.app.web                    -> java.lang                java.base
   com.app.web                    -> com.app.core             classes
   com.app.web                    -> org.slf4j                not found
   com.app.core                   -> java.lang                java.base
   com.app.core                   -> com.app.web              classes
"""


def test_only_edges_between_analysed_packages_survive():
    assert parse(SAMPLE) == {("com.app.web", "com.app.core"), ("com.app.core", "com.app.web")}


def test_a_package_that_only_appears_as_a_target_is_external():
    # org.slf4j never appears on the left, so it is not code we compiled.
    assert not any("slf4j" in b for _, b in parse(SAMPLE))


def test_cross_check_refuses_to_compare_against_a_failed_oracle():
    assert cross_check({"ok": False, "why": "no compiled classes"}, [])["ok"] is False


GRAPH = {"ok": True, "edges": [
    ("a.Mover", "b.Target"),      # the edge we want gone
    ("a.Mover", "a.Neighbour"),   # the cost a package-level view cannot see
    ("a.Other", "a.Mover"),
    ("a.Other", "b.Target"),      # a.Other keeps a -> b alive on its own
]}


def test_a_move_pays_for_the_ties_it_leaves_behind():
    from dsarp.tools.jdeps_runner import move_effect
    e = move_effect(GRAPH, "a.Mover", "b")
    assert e["added"] == [("b", "a")]        # Mover still needs Neighbour, Other still needs Mover
    assert e["removed"] == []                # a -> b survives through a.Other
    assert e["net"] == 1                     # strictly worse, and knowable without building


def test_a_sole_carrier_moving_out_removes_the_edge():
    from dsarp.tools.jdeps_runner import move_effect
    graph = {"ok": True, "edges": [("a.Mover", "b.Target")]}
    e = move_effect(graph, "a.Mover", "b")
    assert e["removed"] == [("a", "b")] and e["added"] == [] and e["net"] == -1


def test_nested_classes_move_with_their_outer_class():
    from dsarp.tools.jdeps_runner import move_effect
    graph = {"ok": True, "edges": [("a.Mover$Inner", "b.Target"), ("a.Mover", "b.Target")]}
    assert move_effect(graph, "a.Mover", "b")["removed"] == [("a", "b")]
