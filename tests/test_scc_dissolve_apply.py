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


def test_build_repair_hook_reruns_compile(monkeypatch, tmp_path):
    builds = iter([{"ok": False, "status": "compile_failed", "javac_errors": ["e"]}, {"ok": True, "status": "compiled"}])
    monkeypatch.setattr(sd, "compile_repo", lambda *a, **k: next(builds))
    hook = lambda copy, stage, text: {"ok": True, "rounds": [{}], "edited": ["X.java"], "stage": stage}
    build, rec = sd._build_with_repair(tmp_path, tmp_path, hook)
    assert build["ok"] and rec["stage"] == "build"


def _stub_measure(monkeypatch, tmp_path, newly_failing):
    """measure with every tool stubbed: counts how often the structural judges run."""
    calls = {"arcan": 0, "api": 0, "cycles": 0}
    (tmp_path / "copy").mkdir()
    monkeypatch.setattr(sd, "_copy_repo", lambda src, dst: tmp_path / "copy")
    monkeypatch.setattr(sd.gates, "before_apply", lambda *a: {"ok": True})
    monkeypatch.setattr(sd.gates, "after_apply", lambda *a: {"ok": True})
    monkeypatch.setattr(sd, "_apply_plan", lambda *a: {"applied": True})
    monkeypatch.setattr(sd, "rewrite_names", lambda *a: [])
    monkeypatch.setattr(sd, "_changed_java", lambda r, c: [tmp_path / "copy" / "src/main/java/a/X.java"])
    monkeypatch.setattr(sd, "compile_repo", lambda *a, **k: {"ok": True, "status": "compiled"})
    def cycles(*a, **k):
        calls["cycles"] += 1
        return {}
    monkeypatch.setattr(sd.au, "cycles", cycles)
    monkeypatch.setattr(sd.gates, "comparable", lambda *a: {"ok": True})
    monkeypatch.setattr(sd.au, "cycle_set", lambda s: [])
    monkeypatch.setattr(sd.au, "edge_map", lambda s: [])
    monkeypatch.setattr(sd.au, "novel_cycles", lambda *a: [])
    monkeypatch.setattr(sd.gates, "dispatch", lambda *a: {"ok": True})
    monkeypatch.setattr(sd, "service_providers", lambda c: {})
    def arcan(*a, **k):
        calls["arcan"] += 1
        return {"by_type": {}}
    monkeypatch.setattr(sd, "detect_with_arcan", arcan)
    monkeypatch.setattr(sd, "_arcan_target_gone", lambda *a: True)
    def api(*a, **k):
        calls["api"] += 1
        return {"ok": True}
    monkeypatch.setattr(sd.api_runner, "report", api)
    monkeypatch.setattr(sd, "_modules", lambda *a: [])
    monkeypatch.setattr(sd, "run_tests", lambda *a, **k: {"status": "ok"})
    fails = iter([newly_failing, []])
    monkeypatch.setattr(sd.gates, "behavioural",
                        lambda b, t: {"state": "PASS", "ok": True, "newly_failing": next(fails)})
    monkeypatch.setattr(sd.gates, "reflection", lambda *a: {"ok": True})
    monkeypatch.setattr(sd.gates, "decide", lambda **k: {"accepted": all(v.get("ok", True) for v in k.values())})
    monkeypatch.setattr(sd.scc_planner, "level", lambda *a: "4c")
    monkeypatch.setattr(sd, "write_patch", lambda *a: tmp_path / "p.patch")
    plan = {"component": ["a", "b"], "size": 2, "moves": [["a.X", "b"]], "predicted_left": 0}
    return calls, plan


def test_tests_stage_repair_rejudges_the_repaired_tree(monkeypatch, tmp_path):
    calls, plan = _stub_measure(monkeypatch, tmp_path, ["a.XTest"])
    hook = lambda c, stage, text, scope: {"ok": True, "edited": ["src/main/java/a/X.java"], "rounds": [{}]}
    row = sd.measure(tmp_path, plan, {"snapshot": {}}, tmp_path, {"t": 1}, "text", False, hook)
    assert calls["cycles"] == 2 and calls["arcan"] == 2 and calls["api"] == 2
    assert row["stage"] == "judged"


def test_repair_that_beats_the_plan_is_rejected():
    row = {"measured_left": 0, "repair": {"build": {"edited": ["X.java"]}, "tests": None}}
    assert sd._repair_overreach(row, {"predicted_left": 2})
    assert not sd._repair_overreach(row, {"predicted_left": 0})
    assert not sd._repair_overreach({"measured_left": 0, "repair": {"build": None, "tests": None}},
                                    {"predicted_left": 2})


def test_no_hook_keeps_old_behaviour(monkeypatch, tmp_path):
    monkeypatch.setattr(sd, "compile_repo", lambda *a, **k: {"ok": False, "status": "compile_failed"})
    build, rec = sd._build_with_repair(tmp_path, tmp_path, None)
    assert not build["ok"] and rec is None
