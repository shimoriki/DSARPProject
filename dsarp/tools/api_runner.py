"""Binary compatibility of a refactoring, reported rather than enforced.

Moves of public classes count as success (decided 2026-11-01), so a break does not reject a
candidate. It has to be visible, per candidate, or a headline rate hides who pays for it.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .arcan_runner import find_mvn

VERSION = "0.26.5"
ARTIFACT = "com.github.siom79.japicmp:japicmp:%s:jar:jar-with-dependencies" % VERSION


def japicmp_jar() -> Optional[Path]:
    """The pinned japicmp, fetched into the local Maven repository on first use."""
    jar = (Path.home() / ".m2/repository/com/github/siom79/japicmp/japicmp" / VERSION
           / ("japicmp-%s-jar-with-dependencies.jar" % VERSION))
    if not jar.exists():
        mvn = find_mvn()
        if mvn:
            subprocess.run([mvn, "-B", "-q", "dependency:get", "-Dartifact=" + ARTIFACT],
                           capture_output=True, text=True, timeout=300)
    return jar if jar.exists() else None


def _jar(classes: Path, target: Path) -> Path:
    subprocess.run(["jar", "cf", str(target), "-C", str(classes), "."], check=True,
                   capture_output=True, timeout=300)
    return target


def incompatibilities(report: str) -> List[str]:
    """japicmp marks a binary-incompatible change with `!` after its status marker."""
    return [ln.strip() for ln in report.splitlines()
            if ln.lstrip().startswith(("***!", "---!", "+++!"))]


def compare(old_classes: Path, new_classes: Path) -> Dict[str, Any]:
    jar = japicmp_jar()
    if not jar:
        return {"ok": False, "measured": False, "why": "japicmp is not available"}
    with tempfile.TemporaryDirectory() as tmp:
        old = _jar(old_classes, Path(tmp) / "old.jar")
        new = _jar(new_classes, Path(tmp) / "new.jar")
        p = subprocess.run(["java", "-jar", str(jar), "-o", str(old), "-n", str(new),
                            "--only-incompatible", "--ignore-missing-classes"],
                           capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        return {"ok": False, "measured": False, "why": (p.stderr or p.stdout)[-300:]}
    breaks = incompatibilities(p.stdout)
    return {"ok": not breaks, "measured": True, "breaks": breaks[:50], "count": len(breaks),
            "why": ("%d binary-incompatible changes" % len(breaks)) if breaks else None}


def report(old_repo: Path, new_repo: Path, modules: List[str]) -> Dict[str, Any]:
    """Compare only modules the change touched; the rest are byte-identical inputs."""
    per = {}
    for module in modules:
        old, new = Path(old_repo) / module / "target/classes", Path(new_repo) / module / "target/classes"
        if old.is_dir() and new.is_dir():
            per[module] = compare(old, new)
    measured = [r for r in per.values() if r.get("measured")]
    count = sum(r.get("count", 0) for r in measured)
    return {"ok": bool(measured) and count == 0, "measured": bool(per) and len(measured) == len(per),
            "count": count, "modules": per,
            "why": ("%d binary-incompatible changes" % count) if count else None}
