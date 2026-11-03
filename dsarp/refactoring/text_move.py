"""Move a class by editing its text, with no parser and no printer in the way.

A move changes one package line, a few imports and the file's directory. Every byte of the rest
should survive, and printing the file from a model is what lost log4j2's "…" default. Whether a
move is legal is still asked of Spoon when the plan is made; this only writes it. References go
through the same `fix_references` as the Spoon arm, so the two differ in the moved file alone.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .java_text import add_origin_imports, drop_same_package_imports, read_source, write_source


def move_classes(repo: Path, moves: List[Tuple[str, str, str]]) -> Dict[str, Any]:
    """Apply (source_root, class, destination package) moves to `repo` in place."""
    from ..tools.spoon_runner import fix_references

    done = []
    for root, fqn, dest in moves:
        old_pkg, simple = fqn.rsplit(".", 1)
        src = Path(root) / (fqn.replace(".", "/") + ".java")
        if not src.is_file():
            return {"applied": False, "why": "no file for %s, is it a secondary type?" % fqn}
        txt, hits = re.subn(r"^(\s*package\s+)%s(\s*;)" % re.escape(old_pkg),
                            lambda m: m.group(1) + dest + m.group(2), read_source(src),
                            count=1, flags=re.M)
        if not hits:
            return {"applied": False, "why": "no package line for %s" % fqn}
        dst = Path(root) / dest.replace(".", "/") / (simple + ".java")
        dst.parent.mkdir(parents=True, exist_ok=True)
        write_source(dst, txt)
        done.append({"type": fqn, "toPackage": dest, "newPath": str(dst), "oldPath": str(src)})
    # Originals stay until now so a sibling that also moves still reads as left behind. Its
    # import is then repointed below like any other reference.
    add_origin_imports(repo, [(m["type"], "%s.%s" % (m["toPackage"], m["type"].rsplit(".", 1)[1]))
                              for m in done])
    for mv in done:
        Path(mv["oldPath"]).unlink()
    fix_references(repo, done)
    for mv in done:
        path = Path(mv["newPath"])
        write_source(path, drop_same_package_imports(read_source(path))[0])
    return {"applied": True}
