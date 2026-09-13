"""Surefire totals must be summed across reactor modules, not read off the last one.

Maven prints one summary per module and no aggregate. Reading the last match reported pdfbox
as 38 tests when it actually ran 2050, and reported log4j2 as "6 failures" while dropping 29
errors from the same run. It also explains the long-standing tika oddity of
status=failed with failures=0: the failure was in a module that was not the last.
"""
from dsarp.tools.arcan_runner import _test_counts

MULTI = """
[INFO] Building Apache PDFBox io
[INFO] Tests run: 21, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 2.2 s -- in io.ATest
[INFO] Tests run: 122, Failures: 0, Errors: 0, Skipped: 0
[INFO] Building Apache FontBox
[ERROR] Tests run: 10, Failures: 2, Errors: 3, Skipped: 1
[INFO] Building Apache PDFBox examples
[INFO] Tests run: 38, Failures: 0, Errors: 0, Skipped: 5
"""


def _sum(text):
    run = f = e = s = 0
    for ln in text.splitlines():
        if "Time elapsed" in ln:
            continue
        c = _test_counts(ln)
        if c is None:
            continue
        run += c[0]; f += c[1]; e += c[2]; s += c[3]
    return run, f, e, s


def test_module_summaries_are_summed_not_overwritten():
    assert _sum(MULTI) == (170, 2, 3, 6)


def test_per_class_lines_are_not_double_counted():
    """The `Time elapsed` line is one test class inside a module already counted."""
    assert _test_counts(
        "[INFO] Tests run: 21, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 2.2 s") \
        == [21, 0, 0, 0]
    assert _sum("[INFO] Tests run: 5, Failures: 0, Errors: 0, Skipped: 0, "
                "Time elapsed: 1 s -- in Foo") == (0, 0, 0, 0)


def test_errors_are_not_dropped():
    """log4j2 reported 6 failures and hid 29 errors; both must survive."""
    assert _sum("[ERROR] Tests run: 950, Failures: 6, Errors: 29, Skipped: 3") \
        == (950, 6, 29, 3)


def test_non_summary_lines_are_ignored():
    assert _test_counts("[INFO] Building Apache FontBox") is None
    assert _test_counts("Tests run: oops") is None
    assert _test_counts("") is None
