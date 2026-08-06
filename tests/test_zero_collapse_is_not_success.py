"""A tool that suddenly finds no smells has stopped seeing the source.

Tika produced Designite 2255 -> 0 with measured=True. The build happened to fail, so the
gate caught it - but that is a 100% reduction headline sitting one build success away. The
same shape as the earlier Arcan 20 -> 0, which was a build that never compiled.
"""
import re
from pathlib import Path

SRC = Path("dsarp/verification/openrewrite_loop.py").read_text(encoding="utf-8")


def test_guard_exists_and_runs_before_the_delta_is_trusted():
    assert 'a_rec.get("smells") == 0' in SRC, "no zero-collapse guard"
    guard = SRC.index('a_rec.get("smells") == 0')
    per_tool = SRC.index('"removed": (b_rec.get("smells") - a_rec.get("smells"))')
    assert guard < per_tool, "the guard must run before a delta is claimed"


def test_guard_only_fires_on_a_meaningful_before_count():
    """A repo that genuinely had 2 smells and now has 0 must still count as fixed."""
    m = re.search(r'\(b_rec\.get\("smells"\) or 0\) >= (\d+)', SRC)
    assert m, "guard should require a minimum before-count"
    assert int(m.group(1)) >= 5, "threshold too low to distinguish a real fix"
