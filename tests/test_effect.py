"""Closed-loop verification tests: applying a refactoring actually removes the smell."""
import shutil
from pathlib import Path

from dsarp.verification.effect_checker import (snapshot_smells, apply_move_class,
                                               apply_break_cycle)

ROOT = Path(__file__).resolve().parent.parent
MINI = ROOT / "data" / "samples" / "mini-java-repo"


def test_snapshot_detects_cycle():
    snap = snapshot_smells(MINI, "mini")
    assert snap.total >= 1
    assert any(len(c) == 2 for c in snap.cycles)  # alpha <-> beta


def test_move_class_removes_cycle(tmp_path):
    copy = tmp_path / "repo"
    shutil.copytree(MINI, copy)
    before = snapshot_smells(copy, "mini")
    assert len(before.cycles) == 1
    res = apply_move_class(copy, "com.example.beta.Beta", "com.example.alpha")
    assert res["applied"] is True
    after = snapshot_smells(copy, "mini")
    assert len(after.cycles) == 0, "moving the class should break the cycle"


def test_break_cycle_moves_crossing_classes(tmp_path):
    copy = tmp_path / "repo"
    shutil.copytree(MINI, copy)
    res = apply_break_cycle(copy, "com.example.alpha", "com.example.beta")
    assert res["applied"] is True and res["count"] >= 1
    after = snapshot_smells(copy, "mini")
    assert len(after.cycles) == 0
