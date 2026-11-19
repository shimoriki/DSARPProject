"""Measure what the instrument reports when nothing architectural changed.

Without this, no delta means anything. Applying one spike to log4j2 moved Arcan's package
cycle sets 140 removed and 108 introduced while the true SCCs barely changed; that is either
the refactoring or the detector, and a placebo is how to tell.

Two arms. REPEAT runs Arcan twice on the same bytecode: any difference is the detector.
NEUTRAL appends a comment to one source file and goes through compile and Arcan: bytecode
should be identical, so any difference is the pipeline.

    py -m dsarp.experiments.placebo <repo> <out>
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

from .arcan_diff import diff
from ..tools import archunit_runner as au
from ..tools.arcan_runner import compile_repo, detect_with_arcan, select_jdk
from ..verification.effect_checker import _copy_repo


def run(repo: Path, out: Path) -> Dict[str, Any]:
    repo, out = Path(repo), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    # Compare two trees built the same way. Against the repository's own build a comment-only
    # edit moved log4j2's largest cycle 50 -> 49, which is the build, not the edit.
    tree = out / "baseline_tree"
    if not tree.exists():
        _copy_repo(repo, tree)
    select_jdk(tree)
    if not compile_repo(tree, log_path=out / "baseline_compile.log", goal="test-compile").get("ok"):
        return {"ok": False, "why": "the baseline copy did not compile"}
    repo = tree
    one = detect_with_arcan(repo, out / "first")
    two = detect_with_arcan(repo, out / "second")
    if not (one.get("measured") and two.get("measured")):
        return {"ok": False, "why": "Arcan did not measure both runs"}
    repeat = diff(out / "first" / "arcan", out / "second" / "arcan")

    copy = out / "copy"
    shutil.rmtree(copy, ignore_errors=True)
    _copy_repo(repo, copy)
    source = next(p for p in sorted(copy.rglob("*.java"))
                  if "src" in p.parts and "main" in p.parts and "test" not in p.parts)
    source.write_text(source.read_text(encoding="utf-8") + "\n// placebo\n", encoding="utf-8")
    built = compile_repo(copy, log_path=out / "compile.log", goal="test-compile")
    if not built.get("ok"):
        return {"ok": False, "why": "the placebo copy did not compile", "repeat": repeat}
    before, after = au.cycles(repo), au.cycles(copy)
    third = detect_with_arcan(copy, out / "neutral")
    neutral = diff(out / "first" / "arcan", out / "neutral" / "arcan")
    shutil.rmtree(copy, ignore_errors=True)
    same = au.cycle_set(before) == au.cycle_set(after)
    clean = (repeat["totals"]["smells_removed"] == repeat["totals"]["smells_introduced"] == 0
             and neutral["totals"]["smells_removed"] == neutral["totals"]["smells_introduced"] == 0)
    return {"ok": bool(third.get("measured")) and same and clean,
            "detector_repeatable": repeat["totals"], "neutral_edit": neutral["totals"],
            "oracle_unchanged": same, "edited": str(source.name),
            "oracle_only_before": sorted(map(sorted, au.cycle_set(before) - au.cycle_set(after))),
            "oracle_only_after": sorted(map(sorted, au.cycle_set(after) - au.cycle_set(before))),
            "class_counts": [before.get("classes"), after.get("classes")]}


if __name__ == "__main__":
    result = run(Path(sys.argv[1]), Path(sys.argv[2]))
    Path(sys.argv[2], "placebo.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
