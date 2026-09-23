"""A second opinion on the package edges, from the JDK's own jdeps.

The edge oracle decides whether a refactoring worked, so a bug in it is not a wrong number in
a table -- it is a wrong verdict on every candidate, in whichever direction the bug leans.
ArchUnit has already been caught being silently blind here: on JDK 26 bytecode its importer
read zero classes and reported success, which would have made "the edge is gone" true for
everything.

jdeps ships with the JDK, reads the same class files through a different implementation, and
has no idea what this project believes. When the two agree on the edge set, the verdict rests
on two independent readings; when they disagree, the disagreement is the finding.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# "   com.foo.a          -> com.foo.b          classes"
_EDGE = re.compile(r"^\s+(\S+)\s+->\s+(\S+)\s+(\S.*)$")


def jdeps_exe() -> Optional[str]:
    home = os.environ.get("JAVA_HOME")
    if home:
        exe = Path(home) / "bin" / ("jdeps.exe" if os.name == "nt" else "jdeps")
        if exe.exists():
            return str(exe)
    return "jdeps"


def parse(out: str) -> Set[Tuple[str, str]]:
    """Package edges between packages that are part of the analysed code.

    A package's own classes always depend on java.lang, so every analysed package appears on
    the left at least once; that set is what "ours" means here. Everything pointing out of it
    -- the JDK, third-party jars, jdeps' "not found" -- is dropped, matching the oracle, which
    only counts dependencies into classes it actually imported.
    """
    pairs = []
    for line in out.splitlines():
        m = _EDGE.match(line)
        if m:
            pairs.append((m.group(1), m.group(2)))
    ours = {a for a, _ in pairs}
    return {(a, b) for a, b in pairs if b in ours and a != b}


def package_edges(class_dirs: List[str], timeout: int = 900) -> Dict[str, Any]:
    """Package edges as jdeps sees them, or why it could not say."""
    dirs = [d for d in class_dirs if Path(d).is_dir()]
    if not dirs:
        return {"ok": False, "why": "no class directories"}
    try:
        p = subprocess.run([jdeps_exe(), "-verbose:package", *dirs],
                           capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "why": f"jdeps unavailable: {exc}"}
    out = (p.stdout or "") + "\n" + (p.stderr or "")
    edges = parse(out)
    # jdeps exits non-zero on unresolved external dependencies, which is normal here and says
    # nothing about the edges among our own packages. Read the edges, not the exit code --
    # but refuse to call an empty reading a success.
    if not edges:
        return {"ok": False, "why": "jdeps reported no internal package edges",
                "returncode": p.returncode, "tail": out[-500:]}
    return {"ok": True, "edges": sorted(edges), "returncode": p.returncode}


def cross_check(oracle: Dict[str, Any], class_dirs: List[str]) -> Dict[str, Any]:
    """Compare the oracle's edge set against jdeps'. Disagreement is reported, not smoothed.

    Perfect agreement is not expected: jdeps works per package on what the constant pool
    records, so a dependency that survives only in a generic signature or an annotation can be
    seen by one and not the other. A handful of edges either way is normal; a large asymmetry
    means one of the two is not reading the code.
    """
    from .archunit_runner import edge_map
    if not oracle.get("ok"):
        return {"ok": False, "why": oracle.get("why") or "oracle run failed"}
    jd = package_edges(class_dirs)
    if not jd.get("ok"):
        return {"ok": False, "why": jd.get("why")}
    a = set(edge_map(oracle))
    b = {tuple(e) for e in jd["edges"]}
    return {"ok": True, "archunit": len(a), "jdeps": len(b), "agreed": len(a & b),
            "only_archunit": sorted(a - b)[:20], "only_jdeps": sorted(b - a)[:20],
            "agreement": round(len(a & b) / max(len(a | b), 1), 3)}
