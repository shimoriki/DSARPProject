"""A delta measured from code that does not compile is not evidence.

Designite parses SOURCE, so it measures a broken tree perfectly happily. That let a run be
stamped `verification_status: "verified"` while `build_after_refactoring` said
`compile_failed` - 21 historical reports carried that contradiction. The gate's whole claim
is that it does not report success it cannot support, so this pins the rule down.
"""
import json
from pathlib import Path

from dsarp.refactoring.outcomes import build_ledger


def test_ledger_ignores_runs_whose_build_broke(tmp_path):
    """The learned ledger must never take a lesson from a tree that did not compile."""
    def report(name, build, delta):
        d = tmp_path / name
        d.mkdir(parents=True)
        (d / "openrewrite_loop_report.json").write_text(json.dumps({
            "build_after_refactoring": build,
            "verification_status": "verified",          # the false label itself
            "delta_by_type": {"Cyclic Dependency": delta},
            "plans": [{"applicable": True, "smell_type": "Cyclic Dependency",
                       "refactoring": "Merge Package"}],
        }), encoding="utf-8")

    report("broken", "compile_failed", -99)   # a huge fake "win" from a broken build
    report("good_1", "compiled", -1)
    report("good_2", "compiled", -1)

    ledger = build_ledger(tmp_path)
    entry = ledger[("Cyclic Dependency", "Merge Package")]
    assert entry["runs"] == 2, "a non-compiling run must not count as evidence"
    assert entry["net"] == -2, f"broken-build delta leaked into the ledger: {entry['net']}"


def test_verified_requires_a_compiling_build():
    """`verified` must imply the code still builds, not merely that both sides measured."""
    src = Path("dsarp/verification/openrewrite_loop.py").read_text(encoding="utf-8")
    assert 'compiled_ok = (after.get("compile") or {}).get("status") == "compiled"' in src
    i, j = src.index("compiled_ok ="), src.index('verification = "verified"')
    assert i < j, "compilation must be established before a verified verdict is reached"
