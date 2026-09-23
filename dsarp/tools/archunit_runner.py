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


def edge_map(result: Dict[str, Any]) -> Dict[tuple, int]:
    """Every package edge in the run, mapped to how many classes carry it.

    Empty for an unsuccessful run; callers must check `ok` first, exactly as with cycle_set.
    """
    if not result.get("ok"):
        return {}
    return {(e["from"], e["to"]): e.get("classes", 1) for e in (result.get("edges") or [])}


def edge_carriers(result: Dict[str, Any], frm: str, to: str) -> List[str]:
    """The class pairs that actually create `frm -> to`, as "Consumer -> Target" FQNs.

    Candidate generation matched the target's simple name in the consumer's source text, which
    cannot see a dependency the compiler introduced and does see one written in a comment. On
    commons-validator that scan named two types for an edge carried by six dependencies, so
    abstracting everything it could see still left the edge standing. This is the compiler's
    own answer, capped on the Java side at thirty pairs per edge.
    """
    if not result.get("ok"):
        return []
    for e in result.get("edges") or []:
        if e.get("from") == frm and e.get("to") == to:
            return list(e.get("carriers") or [])
    return []


def edge_targets(result: Dict[str, Any], frm: str, to: str) -> List[str]:
    """The types in `to` that `frm` depends on — what an inversion would have to abstract."""
    return sorted({p.split(" -> ")[1] for p in edge_carriers(result, frm, to)
                   if " -> " in p})


def edge_verdict(before: Dict[str, Any], after: Dict[str, Any],
                 frm: str, to: str) -> Dict[str, Any]:
    """Did the package edge `frm -> to` disappear, and what did that cost?

    This is the check the project can actually stand behind. Smell counts measure
    participation in a handful of giant components, so a move that detaches a subtree scores
    hundreds while the cycle survives; "this edge is gone" is binary, per candidate, and is
    the property ArchUnit users already write rules about. The cost side is reported next to
    it -- a dependency inversion removes one edge and adds its own -- because an edge count
    that only ever goes down is measuring the wrong direction.
    """
    if not before.get("ok") or not after.get("ok"):
        return {"answerable": False,
                "why": before.get("why") or after.get("why") or "cycle detection failed"}
    eb, ea = edge_map(before), edge_map(after)
    bc, ac = cycle_set(before), cycle_set(after)
    added = sorted(set(ea) - set(eb))
    introduced = sorted(sorted(c) for c in (ac - bc))
    removed = (frm, to) in eb and (frm, to) not in ea
    return {
        "answerable": True,
        "edge": f"{frm} -> {to}",
        "edge_existed": (frm, to) in eb,
        "edge_removed": removed,
        "classes_before": eb.get((frm, to)),
        "classes_after": ea.get((frm, to)),
        "edges_added": ["%s -> %s" % p for p in added],
        "edges_removed": len(set(eb) - set(ea)),
        "cycles_before": len(bc), "cycles_after": len(ac),
        "cycles_introduced": introduced,
        # What is still holding the edge up, so the next attempt aims at it rather than at
        # whatever the text index happened to match.
        "carriers_after": edge_carriers(after, frm, to),
        # The honest headline: the edge is gone and no new cycle appeared in its place.
        "clean": bool(removed and not introduced),
    }
