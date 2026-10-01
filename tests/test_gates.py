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


def test_an_edge_that_vanished_with_its_module_is_not_a_removal():
    # compile_repo drops modules whose dependencies cannot be obtained. The edge is "gone"
    # because nothing compiled it, which reads identically to a successful refactoring.
    from dsarp.verification.gates import comparable
    before = dict(_run([("a", "b", 3)]), classDirs=90, classes=2131)
    after = dict(_run([]), classDirs=74, classes=1700)
    assert not comparable(before, after)["ok"]
    assert not structural(before, after, "a", "b")["ok"]
    assert "failed to build" in structural(before, after, "a", "b")["why"]


def test_losing_the_moved_class_itself_is_within_tolerance():
    from dsarp.verification.gates import comparable
    before = dict(_run([("a", "b", 3)]), classDirs=9, classes=1288)
    after = dict(_run([]), classDirs=9, classes=1287)
    assert comparable(before, after)["ok"]


def test_the_oracle_precedence_is_written_down_where_the_weakest_one_lives():
    # It used to be decided by whichever module a caller happened to import, which is how the
    # product ended up verifying refactorings with a regex index over import statements.
    from dsarp.verification.effect_checker import snapshot_smells
    doc = snapshot_smells.__doc__ or ""
    assert "NOT a verdict" in doc
    assert "AUTHORITATIVE" in doc and "archunit_runner" in doc
    assert "Do not accept a refactoring on it" in doc
