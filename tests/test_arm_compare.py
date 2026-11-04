"""Paired arm comparison: intervals, exact McNemar, and missing rows as failures."""
from dsarp.experiments.arm_compare import compare, mcnemar_exact, wilson


def test_wilson_zero_of_twenty():
    lo, hi = wilson(0, 20)
    assert lo == 0.0 and abs(hi - 0.1611) < 0.001


def test_mcnemar_exact_known_value():
    assert abs(mcnemar_exact(1, 6) - 0.125) < 1e-9 and mcnemar_exact(0, 0) == 1.0


def test_missing_row_counts_as_failure_and_few_targets_get_no_mcnemar():
    ok = {"accepted": True}
    d = [{"repo": "r", "component": ["a", "b"], "level": "4c", "verdict": ok},
         {"repo": "r", "component": ["c", "d"], "level": "4b", "verdict": ok},
         {"repo": "r", "component": ["e", "f"], "level": "4c", "verdict": {"accepted": False}}]
    p = [{"repo": "r", "component": ["a", "b"], "level": "3"}]
    out = compare({"D": d, "P": p})
    assert out["targets"] == 3 and out["arms"]["P"]["levels"] == {"3": 1, "missing": 2}
    assert out["arms"]["D"]["dissolved"] == 1 and "mcnemar" not in out    # the refused 4c is not
