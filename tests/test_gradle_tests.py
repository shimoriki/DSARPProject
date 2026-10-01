"""A Gradle project must be able to get a test verdict, or no refactoring of it can be accepted.

run_tests returned `no_pom` for lucene, solr and spring-framework -- and spring-framework alone
holds 215 of the 457 structural refactorings mined from history. The behavioural gate is the
only gate that can accept a candidate, so those three were unacceptable by construction.
"""
# aliased: pytest would collect a name starting with tests_ as a test function
from dsarp.tools.arcan_runner import _junit_xml_totals, run_tests
from dsarp.tools.arcan_runner import tests_no_worse as no_worse

SUITE = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.app.ThingTest" tests="3" skipped="1" failures="1" errors="0">
  <testcase name="works" classname="com.app.ThingTest"/>
  <testcase name="broken" classname="com.app.ThingTest">
    <failure message="expected 1">assertion failed</failure>
  </testcase>
  <testcase name="ignored" classname="com.app.ThingTest"><skipped/></testcase>
</testsuite>
"""

ERRORED = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.app.OtherTest" tests="1" skipped="0" failures="0" errors="1">
  <testcase name="explodes" classname="com.app.OtherTest">
    <error message="NPE">java.lang.NullPointerException</error>
  </testcase>
</testsuite>
"""


def _reports(root, files):
    d = root / "mod" / "build" / "test-results" / "test"
    d.mkdir(parents=True)
    for name, text in files.items():
        (d / name).write_text(text, encoding="utf-8")
    return root


def test_totals_and_identities_come_out_of_the_junit_xml(tmp_path):
    r = _reports(tmp_path, {"TEST-com.app.ThingTest.xml": SUITE,
                            "TEST-com.app.OtherTest.xml": ERRORED})
    t = _junit_xml_totals(r)
    assert (t["tests_run"], t["failures"], t["errors"], t["skipped"]) == (4, 1, 1, 1)
    # identities, which the surefire console parser has to work much harder for
    assert t["failing_tests"] == ["OtherTest.explodes", "ThingTest.broken"]


def test_gradle_identities_feed_the_same_no_worse_comparison(tmp_path):
    r = _reports(tmp_path, {"TEST-com.app.ThingTest.xml": SUITE})
    before = _junit_xml_totals(r)
    base = {"tests_run": before["tests_run"], "failures": before["failures"],
            "errors": before["errors"], "failing_tests": before["failing_tests"]}
    # the same test still failing is no worse; a different one failing is a regression
    assert no_worse(base, dict(base))["ok"]
    swapped = dict(base, failing_tests=["ThingTest.somethingElse"])
    assert not no_worse(base, swapped)["ok"]


def test_a_malformed_report_does_not_become_a_silent_zero(tmp_path):
    r = _reports(tmp_path, {"TEST-broken.xml": "<testsuite tests='2'"})
    assert _junit_xml_totals(r)["found"] is False


def test_a_project_with_neither_pom_nor_wrapper_still_says_so(tmp_path):
    (tmp_path / "src").mkdir()
    assert run_tests(tmp_path)["status"] == "no_pom"
