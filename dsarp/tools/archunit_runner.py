"""Package cycles from compiled bytecode, and the before/after oracle built on them.

Three orderings have been scored against Arcan's smell-count delta and none generalised. That
target is dominated by one move worth -240 of 325 smells, so a model fitted to it is largely
predicting a single outlier. A cycle is a better unit: present or absent, per candidate, with
no outlier to distort it.

The oracle answers one question -- did the cycle this candidate targeted actually disappear --
and it is deliberately strict about not answering when it cannot know. ArchUnit silently skips
class files whose version its ASM cannot parse, and a silent zero would make "the cycle is
gone" vacuously true for everything; the Java side turns that into a non-zero exit, and this
side refuses to interpret a failed run as good news.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

JAR = (Path(__file__).resolve().parents[2] / "tools" / "dsarp-archunit" / "target"
       / "dsarp-archunit-1.0.0.jar")


def oracle_built() -> bool:
    return JAR.exists()


def class_dirs(repo_path: Path) -> List[str]:
    """Every compiled output directory in the repository.

    Maven puts them at <module>/target/classes. Test classes are excluded: a cycle that exists
    only between test packages is not the production architecture, and including them would
    report cycles no refactoring of main source can close.
    """
    out = []
    for d in Path(repo_path).rglob("target/classes"):
        if d.is_dir() and any(d.rglob("*.class")):
            out.append(str(d))
    return sorted(out)


def cycles(repo_path: Path, log_path: Optional[Path] = None,
           timeout: int = 1800) -> Dict[str, Any]:
    """Package cycles in the repository's compiled classes."""
    if not oracle_built():
        return {"ok": False, "why": "dsarp-archunit jar not built"}
    dirs = class_dirs(repo_path)
    if not dirs:
        return {"ok": False, "why": "no compiled classes found; compile before asking"}
    tmp = Path(tempfile.mkdtemp(prefix="dsarp-cyc-"))
    out = tmp / "cycles.json"
    java = os.environ.get("JAVA_HOME")
    exe = str(Path(java) / "bin" / "java") if java else "java"
    try:
        proc = subprocess.run([exe, "-Xmx3g", "-jar", str(JAR), str(out), *dirs],
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "why": f"cycle detection exceeded {timeout}s"}
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text((proc.stdout or "") + "\n" + (proc.stderr or ""),
                                  encoding="utf-8")
    if not out.exists():
        return {"ok": False, "why": "no output", "tail": (proc.stdout + proc.stderr)[-600:]}
    data = json.loads(out.read_text(encoding="utf-8"))
    data["classDirs"] = len(dirs)
    data["returncode"] = proc.returncode
    return data


def cycle_set(result: Dict[str, Any]) -> Set[frozenset]:
    """The cycles as comparable sets, or empty when the run did not succeed.

    Callers must check `ok` themselves; an unsuccessful run yielding an empty set here is a
    convenience for iteration, never a licence to read it as "no cycles".
    """
    if not result.get("ok"):
        return set()
    return {frozenset(c) for c in (result.get("cycles") or [])}


def containing(cycles_: Set[frozenset], packages: Iterable[str]) -> Set[frozenset]:
    """Cycles that involve any of these packages."""
    want = {p for p in packages if p}
    return {c for c in cycles_ if c & want}


def verdict(before: Dict[str, Any], after: Dict[str, Any],
            packages: Iterable[str]) -> Dict[str, Any]:
    """Did the cycle through `packages` go away, and was anything new created?

    Returns `answerable: False` when either side failed, because "we could not read the
    bytecode" and "there are no cycles" must never collapse into the same answer.
    """
    if not before.get("ok") or not after.get("ok"):
        return {"answerable": False,
                "why": before.get("why") or after.get("why") or "cycle detection failed"}
    b, a = cycle_set(before), cycle_set(after)
    tb, ta = containing(b, packages), containing(a, packages)
    return {
        "answerable": True,
        "targeted_before": len(tb),
        "targeted_after": len(ta),
        "targeted_cycle_removed": bool(tb) and not ta,
        "total_before": len(b),
        "total_after": len(a),
        "cycles_introduced": sorted(sorted(c) for c in (a - b)),
        "cycles_removed": sorted(sorted(c) for c in (b - a)),
        # The honest headline: the targeted cycle is gone AND nothing new appeared.
        "clean_removal": bool(tb) and not ta and not (a - b),
    }
