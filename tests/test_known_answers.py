"""One fixture per measurement bug this project has actually shipped.

Each test states the verdict a correct instrument gives. A later change that reintroduces a
bug fails here, cheaply, instead of in a result someone has already quoted.
"""
from dsarp.refactoring.name_refs import residual
from dsarp.tools.arcan_runner import _test_counts, reactor_skipped, surefire_outcomes
from dsarp.tools.arcan_runner import tests_no_worse as no_worse
from dsarp.tools import jdeps_runner
from dsarp.verification import gates

REACTOR = """
[INFO] Reactor Summary for Apache Log4j BOM 2.26.0-SNAPSHOT:
[INFO]
[INFO] Apache Log4j API ................................... SUCCESS [ 12.1 s]
[INFO] Apache Log4j API Tests ............................. FAILURE [01:03 min]
[INFO] Apache Log4j JSON Template Layout tests ............ SKIPPED
[INFO] Apache Log4j Web ................................... SKIPPED
"""


def test_halted_reactor_names_skipped_modules():
    assert reactor_skipped(REACTOR) == ["Apache Log4j JSON Template Layout tests",
                                        "Apache Log4j Web"]


def test_complete_reactor_skips_nothing():
    assert reactor_skipped("[INFO] Apache Log4j API ..... SUCCESS [ 1 s]") == []


def test_skipped_modules_make_a_run_invalid_not_a_pass():
    base = {"tests_run": 948, "failures": 6, "errors": 29}
    v = gates.behavioural(base, {**base, "partial": True, "skipped_modules": ["x"]})
    assert v["ok"] is False and v["state"] == "INVALID"


def test_partial_baseline_cannot_support_a_pass():
    base = {"tests_run": 948, "failures": 6, "errors": 29, "partial": True}
    v = gates.behavioural(base, {"tests_run": 948, "failures": 6, "errors": 29})
    assert v["ok"] is False and v["state"] == "INVALID"


def test_new_failure_on_partial_run_is_a_real_fail():
    base = {"tests_run": 10, "failures": 0, "errors": 0}
    v = gates.behavioural(base, {"tests_run": 5, "failures": 2, "errors": 0, "partial": True})
    assert v["state"] == "FAIL"


def test_red_baseline_compared_by_identity():
    base = {"outcomes": {"a#x": "passed", "a#y": "failure", "a#z": "passed"}}
    assert no_worse(base, {"outcomes": dict(base["outcomes"])})["ok"]
    worse = no_worse(base, {"outcomes": {"a#x": "failure", "a#y": "passed", "a#z": "passed"}})
    assert not worse["ok"] and worse["newly_failing"] == ["a#x"]


def test_a_test_that_stopped_running_is_caught_by_identity():
    base = {"outcomes": {"a#x": "passed", "a#y": "passed"}}
    v = no_worse(base, {"outcomes": {"a#x": "passed"}})
    assert not v["ok"] and v["tests_not_run"] == 1


def test_surefire_xml_gives_per_test_outcomes(tmp_path):
    d = tmp_path / "m" / "target" / "surefire-reports"
    d.mkdir(parents=True)
    (d / "TEST-a.xml").write_text(
        '<testsuite><testcase classname="a.B" name="ok"/>'
        '<testcase classname="a.B" name="bad"><failure/></testcase>'
        '<testcase classname="a.B" name="off"><skipped/></testcase></testsuite>')
    assert surefire_outcomes(tmp_path) == {"a.B#ok": "passed", "a.B#bad": "failure",
                                           "a.B#off": "skipped"}


def test_totals_read_all_four_numbers():
    assert list(_test_counts("Tests run: 7, Failures: 1, Errors: 2, Skipped: 3")) == [7, 1, 2, 3]


def test_broken_build_is_not_a_clean_result():
    assert not gates.comparable({"classDirs": 39, "classes": 3121},
                                {"classDirs": 2, "classes": 88})["ok"]


def test_a_name_that_extends_the_old_name_is_not_a_residual(tmp_path):
    (tmp_path / "A.java").write_text("import com.app.ThingDefaults;\n", encoding="utf-8")
    assert residual(tmp_path, "com.app.Thing")["ok"]
    (tmp_path / "B.java").write_text("import com.app.Thing;\n", encoding="utf-8")
    assert not residual(tmp_path, "com.app.Thing")["ok"]


def test_nested_use_of_the_old_name_is_a_residual(tmp_path):
    (tmp_path / "C.java").write_text("import com.app.Thing.Inner;\n", encoding="utf-8")
    assert not residual(tmp_path, "com.app.Thing")["ok"]


def test_jdeps_reads_each_directory_alone(monkeypatch, tmp_path):
    """Passing log4j2's 39 directories together crashes jdeps in module resolution."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    seen = []

    class Done:
        stdout = "   p.A  -> q.B  not found\n   q.B  -> p.A  not found\n"
        stderr = ""
        returncode = 0

    def fake(cmd, **_):
        seen.append(cmd)
        return Done()

    monkeypatch.setattr(jdeps_runner.subprocess, "run", fake)
    assert jdeps_runner.class_edges([str(a), str(b)])["ok"]
    assert len(seen) == 2 and all(len([c for c in cmd if str(tmp_path) in c]) == 1 for cmd in seen)


def test_service_order_change_is_a_failure():
    before = {"svc": ["a.First", "b.Second"]}
    after = {"svc": ["a.First", "z.moved.Second"]}
    assert gates.dispatch(before, after, {"b.Second": "z.moved.Second"})["ok"]
    after = {"svc": ["a.First", "0.moved.Second"]}
    assert not gates.dispatch(before, after, {"b.Second": "0.moved.Second"})["ok"]


def test_lost_provider_is_a_failure():
    assert not gates.dispatch({"svc": ["a.B"]}, {"svc": []}, {})["ok"]


def test_invalid_outranks_a_passing_gate():
    v = gates.decide(structural={"ok": True},
                     behavioural={"ok": False, "state": "INVALID", "why": "skipped"})
    assert v["accepted"] is False and v["state"] == "INVALID"


def test_pass_needs_every_gate():
    assert gates.decide(structural={"ok": True}, behavioural={"ok": True})["state"] == "PASS"
    assert gates.decide(structural={"ok": False, "why": "x"},
                        behavioural={"ok": True})["state"] == "FAIL"
