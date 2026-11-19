"""Dry run of a mixed plan: moves first, then each inversion alone on the moved tree."""
from dsarp.experiments import mixed_plan


def test_one_edit_per_implementation_named_as_after_the_moves():
    ed = mixed_plan.to_edits([["x", "y.C"], ["x", "y.B"]], [["y.B", "z"]])
    assert [(e["type"], e["types"], e["toPackage"]) for e in ed] == \
        [("z.B", ["z.B"], "x"), ("y.C", ["y.C"], "x")]


def test_any_refused_inversion_refuses_the_plan(tmp_path, monkeypatch):
    (tmp_path / "repo").mkdir()
    monkeypatch.setattr(mixed_plan, "precheck_by_module", lambda copy, edits, facts, log_dir: {
        "legal": [{"edit": edits[0]}], "illegal": [{"edit": edits[1], "why": "constructed"}]})
    r = mixed_plan.dry_run(tmp_path / "repo", {"inversions": [["x", "y.B"], ["x", "y.C"]]}, tmp_path / "w")
    assert r == {"ok": False, "refused": "y.C", "why": "constructed"}


def test_moves_only_needs_no_precheck(tmp_path, monkeypatch):
    import dsarp.experiments.scc_dissolve as sd
    (tmp_path / "repo").mkdir()
    monkeypatch.setattr(sd, "_apply", lambda copy, moves, work, engine: {"applied": True})
    monkeypatch.setattr(mixed_plan, "precheck_by_module", None)
    assert mixed_plan.dry_run(tmp_path / "repo", {"moves": [["a.B", "c"]]}, tmp_path / "w")["ok"]
