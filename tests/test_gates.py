"""Each gate exists because a candidate got the wrong verdict without it."""
from dsarp.verification.gates import behavioural, decide, structural


def _run(edges, cycles=()):
    return {"ok": True, "cycles": [list(c) for c in cycles],
            "edges": [{"from": f, "to": t, "classes": n} for f, t, n in edges]}


BEFORE = _run([("a", "b", 3), ("b", "a", 1)], cycles=[("a", "b", "c")])
BASE_TESTS = {"tests_run": 2050, "failures": 0, "errors": 0}


def test_a_shrinking_cycle_still_passes_the_structural_gate():
    after = _run([("a", "b", 3)], cycles=[("a", "b")])
    assert structural(BEFORE, after, "b", "a")["ok"]


def test_the_structural_gate_says_which_way_it_failed():
    same = structural(BEFORE, BEFORE, "b", "a")
    assert not same["ok"] and "still there" in same["why"]


def test_an_unreadable_oracle_is_a_failure_not_a_pass():
    assert not structural(BEFORE, {"ok": False, "why": "no classes"}, "b", "a")["ok"]


def test_tests_that_stopped_running_are_named_as_such():
    v = behavioural(BASE_TESTS, {"tests_run": 1994, "failures": 0, "errors": 0})
    assert not v["ok"] and "stopped running" in v["why"]


def test_a_candidate_is_accepted_only_when_every_gate_ran_and_passed():
    ok = {"ok": True}
    assert decide(after_apply=ok, structural=ok, behavioural=ok)["accepted"]
    d = decide(after_apply=ok, structural=ok,
               behavioural={"ok": False, "why": "3 new failures"})
    assert not d["accepted"] and d["failed_gate"] == "behavioural"
    assert d["why"] == "3 new failures"


def test_text_references_warn_but_do_not_refuse():
    # pdfbox's pom named the moved class; the answer was to rewrite the pom, not to give up
    d = decide(before_apply={"ok": False, "why": "1 file names this class as text"},
               after_apply={"ok": True}, structural={"ok": True}, behavioural={"ok": True})
    assert d["accepted"] and d["warnings"]["before_apply"]


def test_a_skipped_test_run_cannot_accept():
    assert not decide(structural={"ok": True}, behavioural=behavioural(BASE_TESTS, None))[
        "accepted"]
