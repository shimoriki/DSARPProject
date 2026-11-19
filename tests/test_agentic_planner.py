from tests.conftest import Scripted
from dsarp.agentic.planner import llm_plan, parse_ops, validate

EDGES = {("a.X", "b.Y"), ("b.Y", "a.Z")}          # a <-> b
OK = '{"operations":[{"op":"moveClass","class":"b.Y","to":"a"}],"rationale":"r"}'


def test_parse_takes_first_json_inside_fence():
    ops, errs = parse_ops("Sure!\n```json\n" + OK + "\n```")
    assert ops == [("move", "b.Y", "a")] and errs == []


def test_unknown_and_nested_names_rejected():
    v = validate([("move", "b.Y$Inner", "a"), ("move", "Y", "a")], EDGES, {"a", "b"}, lambda c, d: True, None)
    assert [r[1] for r in v["rejected"]] == ["unknown class", "unknown class"]


def test_feedback_then_dissolving_plan():
    bad = '{"operations":[{"op":"moveClass","class":"b.Nope","to":"a"}]}'
    m = Scripted(bad, OK)
    plan = llm_plan(m, EDGES, {"a", "b"}, lambda c, d: True, None, rounds=3)
    assert plan["moves"] == [["b.Y", "a"]] and plan["predicted_left"] == 0 and plan["dissolves"]
    assert "b.Nope: unknown class" in m.prompts[1] and len(plan["rounds"]) == 2


def test_plan_pulling_outside_package_into_cycle_is_rejected():
    edges = EDGES | {("c.Q", "a.X")}
    pull = '{"operations":[{"op":"moveClass","class":"a.X","to":"c"}]}'
    plan = llm_plan(Scripted(pull, pull, pull), edges, {"a", "b"}, lambda c, d: True, None, rounds=3)
    assert plan["moves"] == [] and plan["predicted_left"] == 2


def test_model_down_is_recorded_not_raised():
    class Down:
        def generate(self, *a, **k): raise RuntimeError("unreachable")
    plan = llm_plan(Down(), EDGES, {"a", "b"}, lambda c, d: True, None)
    assert plan["moves"] == [] and plan["why"].startswith("model call failed")
