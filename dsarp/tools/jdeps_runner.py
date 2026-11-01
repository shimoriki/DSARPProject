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
    run = _each_directory("-verbose:package", class_dirs, timeout)
    if not run["ok"]:
        return run
    out, returncode = run["out"], run["returncode"]
    edges = parse(out)
    # jdeps exits non-zero on unresolved external dependencies, which is normal here and says
    # nothing about the edges among our own packages. Read the edges, not the exit code --
    # but refuse to call an empty reading a success.
    if not edges:
        return {"ok": False, "why": "jdeps reported no internal package edges",
                "returncode": returncode, "tail": out[-500:]}
    return {"ok": True, "edges": sorted(edges), "returncode": returncode}


def _each_directory(flag: str, class_dirs: List[str], timeout: int) -> Dict[str, Any]:
    """jdeps output for every directory, read one at a time.

    Passing log4j2's 39 directories in one command crashes jdeps inside
    java.lang.module.Configuration.resolve, and the edges come back empty. Adding them as -cp
    fails the same way, silently, with a partial graph. One process per directory costs a few
    JVM starts and works; an edge into another directory is still reported, as "not found".
    """
    dirs = [d for d in class_dirs if Path(d).is_dir()]
    if not dirs:
        return {"ok": False, "why": "no class directories"}
    chunks, returncode = [], 0
    for d in dirs:
        try:
            p = subprocess.run([jdeps_exe(), flag, d],
                               capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "why": f"jdeps unavailable: {exc}"}
        chunks += [p.stdout or "", p.stderr or ""]
        returncode = returncode or p.returncode
    return {"ok": True, "out": "\n".join(chunks), "returncode": returncode}


def class_edges(class_dirs: List[str], timeout: int = 900) -> Dict[str, Any]:
    """The class-level dependency graph, same-package edges included.

    `-verbose:package` and `-verbose:class` both hide dependencies inside a package, and those
    are exactly the ones that decide what a move costs: a class leaving its package turns every
    tie to its former neighbours into a new package edge. ArchUnit drops them too, for the good
    reason that a package cannot be in a cycle with itself.
    """
    run = _each_directory("-verbose", class_dirs, timeout)
    if not run["ok"]:
        return run
    out = run["out"]
    pairs = []
    for line in out.splitlines():
        m = _EDGE.match(line)
        if m:
            pairs.append((m.group(1), m.group(2)))
    ours = {a.rsplit(".", 1)[0] for a, _ in pairs}
    edges = {(a, b) for a, b in pairs if b.rsplit(".", 1)[0] in ours and a != b}
    if not edges:
        return {"ok": False, "why": "jdeps reported no internal class edges",
                "tail": out[-500:]}
    return {"ok": True, "edges": sorted(edges)}


def move_effect(graph: Dict[str, Any], cls, to_package: str) -> Dict[str, Any]:
    """Exactly which package edges appear and disappear if `cls` moves to `to_package`.

    Relabel one class and re-derive the package graph: no heuristic, no build, and it accounts
    for the term a package-level view cannot see, which is the moved class's ties to the
    package it is leaving. Those usually dominate -- a class with five neighbours at home
    trades one edge for five.

    Nested classes move with their outer class, which is what moving the file does. `cls` may
    be one class or several moving together -- an edge carried by three classes needs all
    three to move before it goes, and the three then stop paying for each other's ties.
    """
    if not graph.get("ok"):
        return {"ok": False, "why": graph.get("why")}
    group = [cls] if isinstance(cls, str) else list(cls)
    pkg = lambda c: c.rsplit(".", 1)[0]
    moved = lambda c: (to_package if any(c == m or c.startswith(m + "$") for m in group)
                       else pkg(c))
    before, after = set(), set()
    for a, b in graph["edges"]:
        if pkg(a) != pkg(b):
            before.add((pkg(a), pkg(b)))
        if moved(a) != moved(b):
            after.add((moved(a), moved(b)))
    return {"ok": True, "removed": sorted(before - after), "added": sorted(after - before),
            "net": len(after - before) - len(before - after)}


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
