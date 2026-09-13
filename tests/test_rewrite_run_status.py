"""A build that exits 0 having changed nothing is not the same as a clean run.

The failure this guards: on a big repo Maven cannot resolve the dependency classpath, so
OpenRewrite parses the sources WITHOUT type attribution, every type-based recipe matches
nothing, and the build exits 0. Collapsing that into "clean" reports a successful no-op
refactoring, which is the most misleading outcome the loop can record.
"""
from dsarp.openrewrite.runner import _classify, _first_errors

OOM = "[INFO] Scanning\njava.lang.OutOfMemoryError: Java heap space\n"
NO_DEPS = ("[WARNING] Could not resolve dependencies for project org.apache:spark\n"
           "[INFO] BUILD SUCCESS\n")


def test_classify():
    assert _classify("Changes have been made to X by:", 0, True) == "changed"
    assert _classify(OOM, 1, False) == "oom"
    assert _classify(NO_DEPS, 0, False) == "clean_no_types"
    assert _classify("[INFO] BUILD SUCCESS", 0, False) == "clean"
    assert _classify("[ERROR] Failed to execute goal", 1, False) == "failed"
    # OOM outranks the exit code: a heap death also exits non-zero.
    assert _classify(OOM, 0, False) == "oom"


def test_first_errors_reads_the_head_not_the_tail():
    log = "\n".join(["[INFO] noise"] * 500 + ["[ERROR] real cause in module core"]
                    + ["[INFO] reactor summary"] * 500)
    assert _first_errors(log) == ["[ERROR] real cause in module core"]


if __name__ == "__main__":
    test_classify()
    test_first_errors_reads_the_head_not_the_tail()
    print("ok")
