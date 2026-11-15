import pytest

from dsarp.experiments import scc_dissolve as sd


def test_apply_plan_moves_then_inverts(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(sd, "_apply", lambda c, m, w, e: calls.append(("moves", m, e)) or {"applied": True})
    monkeypatch.setattr(sd, "_apply_inversions", lambda c, edits, w: calls.append(("inv", edits)) or {"applied": True})
    plan = {"moves": [["p.A", "q"]], "inversions": [["q", "p.A"]]}
    assert sd._apply_plan(tmp_path, plan, tmp_path, "text") == {"applied": True}
    assert calls[0] == ("moves", [["p.A", "q"]], "text")
    assert calls[1][1][0]["type"] == "q.A"          # inversion names the moved class's new name


def test_apply_plan_stops_when_moves_fail(monkeypatch, tmp_path):
    monkeypatch.setattr(sd, "_apply", lambda *a: {"applied": False, "why": "x"})
    monkeypatch.setattr(sd, "_apply_inversions", lambda *a: pytest.fail("must not run"))
    assert sd._apply_plan(tmp_path, {"moves": [["p.A", "q"]], "inversions": [["q", "p.A"]]}, tmp_path, "text")["applied"] is False


def test_arm_matches_fills_old_defaults():
    arm = {"engine": "text", "facades": True, "operators": "moves", "repair": False}
    assert sd.arm_matches({"engine": "text", "facades": True}, arm)
    assert not sd.arm_matches({"engine": "spoon", "facades": True}, arm)
    llm = {**arm, "operators": "mixed", "planner": "llm", "model": "m"}
    assert not sd.arm_matches(arm, llm)
