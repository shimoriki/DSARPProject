import json

import pytest

from dsarp.agentic import run
from dsarp.agentic.run import targets_from


def test_targets_from_reads_components(tmp_path):
    p = tmp_path / "preregistration.json"
    p.write_text(json.dumps({"plans": [{"component": ["a", "b"]}, {"component": ["c", "d", "e"]}]}))
    assert targets_from(p) == [["a", "b"], ["c", "d", "e"]]


def test_spoon_refusal_bans_and_replans(monkeypatch, tmp_path):
    seen = []

    def fake_plan(model, edges, comp, accept, blocked, rounds=3):
        seen.append(accept("b.Y", "a"))
        return {"component": sorted(comp), "size": 2, "moves": [["b.Y", "a"]], "inversions": [],
                "predicted_left": 0, "dissolves": True, "planner": "llm", "rounds": []}
    verdicts = iter([{"ok": False, "refused": "b.Y", "why": "visibility"}, {"ok": True}])
    monkeypatch.setattr(run, "llm_plan", fake_plan)
    monkeypatch.setattr(run, "dry_run", lambda *a: next(verdicts))
    monkeypatch.setattr(run, "_accept_for", lambda repo, banned: (lambda c, d: c not in banned))
    plans = run.make_llm_plans(tmp_path, {"edges": [["a.X", "b.Y"], ["b.Y", "a.Z"]], "snapshot": {}},
                               object(), [["a", "b"]], tmp_path)
    assert seen == [True, False] and plans[0]["refused"] == ["b.Y"]


def test_refused_inversion_is_blocked_next_attempt(monkeypatch, tmp_path):
    seen = []

    def fake_plan(model, edges, comp, accept, blocked, rounds=3):
        seen.append(blocked("a", "b.Y", {}))
        return {"component": sorted(comp), "size": 2, "moves": [], "inversions": [["a", "b.Y"]],
                "predicted_left": 0, "dissolves": True, "planner": "llm", "rounds": []}
    verdicts = iter([{"ok": False, "refused": "b.Y", "why": "static use"}, {"ok": True}])
    monkeypatch.setattr(run, "llm_plan", fake_plan)
    monkeypatch.setattr(run, "dry_run", lambda *a: next(verdicts))
    monkeypatch.setattr(run, "_accept_for", lambda repo, banned: (lambda c, d: True))
    monkeypatch.setattr(run.InversionFacts, "blocked", lambda self, p, i, m: None)
    run.make_llm_plans(tmp_path, {"edges": [["a.X", "b.Y"], ["b.Y", "a.Z"]], "snapshot": {}},
                       object(), [["a", "b"]], tmp_path)
    assert seen[0] is None and seen[1] == "refused by Spoon"


def test_confirm_refuses_other_arm(tmp_path):
    (tmp_path / "preregistration.json").write_text(json.dumps(
        {"arm": {"engine": "text", "facades": True, "operators": "moves", "repair": False}, "plans": []}))
    with pytest.raises(SystemExit, match="frozen for"):
        run.check_frozen(tmp_path, {"engine": "text", "facades": True, "operators": "mixed",
                                    "repair": False, "planner": "llm", "model": "m"})
