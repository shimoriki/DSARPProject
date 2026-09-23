"""jdeps is the second reading of the same bytecode; it must agree about our packages only.

ArchUnit was once silently blind on newer class files and still reported success, so the
oracle's verdicts now rest on two independent readers rather than one.
"""
from dsarp.tools.jdeps_runner import cross_check, parse

SAMPLE = """classes -> java.base
classes -> not found
   com.app.web                    -> java.lang                java.base
   com.app.web                    -> com.app.core             classes
   com.app.web                    -> org.slf4j                not found
   com.app.core                   -> java.lang                java.base
   com.app.core                   -> com.app.web              classes
"""


def test_only_edges_between_analysed_packages_survive():
    assert parse(SAMPLE) == {("com.app.web", "com.app.core"), ("com.app.core", "com.app.web")}


def test_a_package_that_only_appears_as_a_target_is_external():
    # org.slf4j never appears on the left, so it is not code we compiled.
    assert not any("slf4j" in b for _, b in parse(SAMPLE))


def test_cross_check_refuses_to_compare_against_a_failed_oracle():
    assert cross_check({"ok": False, "why": "no compiled classes"}, [])["ok"] is False
