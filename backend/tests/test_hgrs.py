import pytest

from dsarp.hgrs import DEFAULT_WEIGHTS, compute_hgrs, validate_weights


def test_weights_sum_to_one():
    assert sum(validate_weights(DEFAULT_WEIGHTS).values()) == pytest.approx(1.0)


def test_hgrs_all_fives():
    scores = {c: 5 for c in DEFAULT_WEIGHTS}
    assert compute_hgrs(scores) == 5.0


def test_hgrs_weighted_example():
    scores = {
        "evidence_grounding": 4, "refactoring_relevance": 3,
        "architectural_reasoning": 5, "minimality_and_safety": 2,
        "actionability": 4, "human_confidence": 3, "cost_efficiency": 5,
    }
    expected = (0.25 * 4 + 0.20 * 3 + 0.15 * 5 + 0.15 * 2
                + 0.10 * 4 + 0.10 * 3 + 0.05 * 5)
    assert compute_hgrs(scores) == pytest.approx(round(expected, 3))


def test_hgrs_rejects_out_of_range():
    scores = {c: 3 for c in DEFAULT_WEIGHTS}
    scores["actionability"] = 6
    with pytest.raises(ValueError):
        compute_hgrs(scores)


def test_hgrs_rejects_missing_criterion():
    scores = {c: 3 for c in DEFAULT_WEIGHTS}
    scores.pop("cost_efficiency")
    with pytest.raises(ValueError):
        compute_hgrs(scores)
