"""The reach probe's stop rule counts only Arcan-reported SCCs that the mix alone makes dissolvable."""
from dsarp.experiments.reach_probe import holdout, summarise


def row(arcan, moves, mixed):
    cell = lambda d: {"dissolvable": d}
    return {"repo": "r", "arcan_reported": arcan, "moves_only": cell(moves), "mixed": cell(mixed)}


def test_ten_arcan_reported_mix_wins_pass():
    s = summarise([row(True, False, True)] * 10 + [row(False, False, True)] * 5 + [row(True, True, True)] * 3)
    assert s["mix_extra_dissolvable"] == 10 and s["stop_rule_passed"]
    assert s["unreported_dissolvable_by_mix"] == 5


def test_nine_fail():
    assert not summarise([row(True, False, True)] * 9)["stop_rule_passed"]


def test_holdout_comes_from_the_fixed_pool():
    held = holdout()
    assert "apache-commons-math" in held and "apache-commons-net" not in held and len(held) == 19
