"""Places a type is named as TEXT, where moving it changes nothing that the compiler checks.

A move renames the type. Every reference the compiler can see is rewritten with it, which is
why eighteen moves compiled and eighteen removed their edge. What the compiler cannot see is a
name written as a string: a service file listing an implementation, a class named in XML, a
`Class.forName("...")`, a resource looked up beside a package. Those keep pointing at the old
name and fail at run time, if anything exercises them.

This is the cheap end of that check -- a text scan of the repository, seconds, before anything
is applied. It cannot prove a move is safe: tika's ParseContext moves broke thirty-seven tests
and are not caught here, because nothing names that class as a string. It catches the cases it
can name, and the test run remains the verdict.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

# Files that carry class names the compiler never reads.
_TEXT_SUFFIXES = (".xml", ".properties", ".json", ".yaml", ".yml", ".cfg", ".conf",
                  ".txt", ".MF", ".factories", ".handlers", ".schemas", ".tld")
_SKIP_DIRS = {"target", "build", ".git", "node_modules"}
_MAX_BYTES = 2_000_000


def _candidate_files(repo_path: Path):
    for p in Path(repo_path).rglob("*"):
        if not p.is_file():
            continue
        if _SKIP_DIRS & set(p.parts):
            continue
        if p.suffix in _TEXT_SUFFIXES or "META-INF/services" in p.as_posix() \
                or p.suffix == ".java":
            try:
                if p.stat().st_size <= _MAX_BYTES:
                    yield p
            except OSError:
                continue


def name_references(repo_path: Path, fqn: str) -> Dict[str, Any]:
    """Where `fqn` is written as text rather than as a resolved reference.

    Java hits count only inside string literals: an import or a normal use is exactly what the
    refactoring rewrites, and flagging those would flag every candidate.
    """
    repo_path = Path(repo_path)
    in_string = re.compile(r'"[^"\n]*' + re.escape(fqn) + r'[^"\n]*"')
    resources: List[str] = []
    literals: List[str] = []
    for p in _candidate_files(repo_path):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if fqn not in text:
            continue
        rel = p.relative_to(repo_path).as_posix()
        if p.suffix == ".java":
            if in_string.search(text):
                literals.append(rel)
        else:
            resources.append(rel)
    return {"fqn": fqn, "resources": sorted(resources)[:20],
            "string_literals": sorted(literals)[:20],
            "count": len(resources) + len(literals),
            # Not "unsafe" -- "the compiler will not fix these for you".
            "needs_manual_fixup": bool(resources or literals)}


def declared_public(repo_path: Path, fqn: str) -> bool:
    """Is this type public? Moving one renames it for every downstream build.

    Nothing in a dependency graph can see this cost. pdfbox's Loader and COSObjectable are
    public API, so the two cleanest moves measured here are also major-version changes for
    everyone who depends on the library -- which a maintainer weighs, and a tool should say
    out loud rather than count as a win.
    """
    rel = fqn.replace(".", "/") + ".java"
    simple = fqn.rsplit(".", 1)[-1]
    for p in Path(repo_path).rglob(simple + ".java"):
        if p.as_posix().endswith(rel) and "target" not in p.parts:
            head = p.read_text(encoding="utf-8", errors="ignore")
            return re.search(r"\bpublic\s+(?:final\s+|abstract\s+|sealed\s+)*"
                             r"(?:class|interface|enum|record|@interface)\s+" + simple,
                             head) is not None
    return False


def residual(repo_path: Path, fqn: str) -> Dict[str, Any]:
    """Files that still mention `fqn` after it was supposed to have moved away.

    A post-condition no applier should fail and two did. OpenRewrite 5.42.1 relocated
    org.apache.pdfbox.Loader and left two test files importing the old name; 6.46.1 relocated
    log4j2's @Required and left RegexFilter.java importing and using it. Both produced a
    "changed" status, both broke the build, and both cost a full compile to discover -- this
    costs seconds and is the same answer.

    Unlike name_references, ordinary Java references count here: once the type has moved,
    nothing should name the old one.
    """
    repo_path = Path(repo_path)
    hits: List[str] = []
    # A bare substring test fails valid moves: com.app.Thing is inside com.app.ThingDefaults.
    named = re.compile(r"(?<![\w$])" + re.escape(fqn) + r"(?![\w$])")
    for p in _candidate_files(repo_path):
        try:
            if named.search(p.read_text(encoding="utf-8", errors="ignore")):
                hits.append(p.relative_to(repo_path).as_posix())
        except OSError:
            continue
    return {"fqn": fqn, "ok": not hits, "files": sorted(hits)[:20], "count": len(hits)}
