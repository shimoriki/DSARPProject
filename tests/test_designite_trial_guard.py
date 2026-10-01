"""The trial edition of Designite reports nothing above 50k lines, and says so only in its log.

Nothing fails when it refuses: every CSV is written with its header row and no rows, the exit code
is zero, and the repository reads as having no smells at all. apache-commons-io came back as a
clean zero that way. A reduction measured against that baseline would be meaningless, so both the
measurement and the addressability analysis have to refuse the directory outright.
"""
from dsarp.experiments.addressable import analyse
from dsarp.experiments.smell_reduction import trial_limit_hit

HEADER = ("Project,Package,Class,Method,Smell,Description,Method start line no,File\n")
REFUSED = """\
02-10-2026 00:59:37: Detecting code smells...
02-10-2026 00:59:39: The trial version allows you to analyze an application lesser than 50000 \
lines of code in size. The selected application has crossed the threshold, therefore the \
detailed results are disabled.
02-10-2026 00:59:48: Done.
"""
FINE = """\
02-10-2026 00:59:37: Detecting code smells...
02-10-2026 00:59:48: Done.
Total time (sec): 12
"""


def _tree(tmp_path, log_text, rows=""):
    (tmp_path / "DesigniteLog02102026_0059.txt").write_text(log_text, encoding="utf-8")
    for name in ("ImplementationSmells", "DesignSmells", "ArchitectureSmells"):
        (tmp_path / (name + ".csv")).write_text(HEADER + rows, encoding="utf-8")
    return tmp_path


def test_the_refusal_is_detected(tmp_path):
    assert "crossed the threshold" in trial_limit_hit(_tree(tmp_path, REFUSED))


def test_a_normal_run_is_not_mistaken_for_a_refusal(tmp_path):
    assert trial_limit_hit(_tree(tmp_path, FINE)) is None


def test_an_empty_result_from_a_refusal_is_not_reported_as_zero_smells(tmp_path):
    a = analyse(_tree(tmp_path, REFUSED))
    assert a.get("ok") is False and a.get("trial_limited") is True
    assert a["reachable_pct"] is None, "a refused run must not produce a percentage"


def test_a_genuinely_clean_repository_still_measures(tmp_path):
    # No rows, but no refusal either: that is a real answer and must not be confused with one.
    a = analyse(_tree(tmp_path, FINE))
    assert a.get("ok") is True
    assert a["production_smells"] == 0
