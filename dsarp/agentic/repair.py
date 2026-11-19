"""Compiler and tester repair agent: small search/replace edits, scoped to the files the plan touched.

The model may only edit main-source files the plan changed. It never touches tests, build files or
service files, and may not hide a dependency behind a reflective lookup. Each edit's search text
must match exactly once. The plan itself is never changed; acceptance stays with the gates.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Set

from ..verification.gates import REFLECTIVE
from .planner import _first_json

_JAVA_ERROR = re.compile(r"^\[ERROR\].*\.java\b")
MAX_LINES = 400


def error_summary(log_text: str, limit: int = 20) -> List[str]:
    out: List[str] = []
    for line in log_text.splitlines():
        line = line.rstrip()
        if _JAVA_ERROR.match(line) and line not in out:
            out.append(line)
            if len(out) >= limit:
                break
    return out


def parse_edits(text: str) -> List[Dict[str, str]]:
    obj = _first_json(text or "") or {}
    return [{"path": str(e["path"]), "search": str(e["search"]), "replace": str(e["replace"])}
            for e in obj.get("edits") or []
            if isinstance(e, dict) and all(k in e for k in ("path", "search", "replace"))]


def _why_not(copy: Path, rel: str, allowed: Set[str]) -> str:
    norm = rel.replace("\\", "/")
    target = (copy / norm).resolve()
    if copy.resolve() not in target.parents:
        return "outside working copy"
    if "src/test/" in "/" + norm:
        return "test source"
    name = norm.rsplit("/", 1)[-1]
    if name == "pom.xml" or name.endswith(".gradle") or name.endswith(".gradle.kts") or "META-INF/" in norm:
        return "build file"
    if norm not in allowed:
        return "not in scope"
    return ""


def apply_edits(copy: Path, edits: List[Dict[str, str]], allowed: Set[str]) -> Dict[str, Any]:
    allowed = {a.replace("\\", "/") for a in allowed}
    applied: List[str] = []
    refused: List[List[str]] = []
    for e in edits:
        rel = e["path"].replace("\\", "/")
        why = _why_not(copy, rel, allowed)
        if not why and any(t in e["replace"] and t not in e["search"] for t in REFLECTIVE):
            why = "adds a reflective lookup"
        text = ""
        if not why:
            try:
                text = (copy / rel).read_text(encoding="utf-8")
            except UnicodeDecodeError:          # old Apache sources carry Latin-1 author names
                why = "not utf-8"
        if not why:
            n = text.count(e["search"]) if e["search"] else 0
            if n != 1:
                why = "search matched %d times" % n
            else:
                (copy / rel).write_text(text.replace(e["search"], e["replace"], 1), encoding="utf-8")
                applied.append(rel)
        if why:
            refused.append([rel, why])
    return {"applied": applied, "refused": refused}


def _prompt(copy: Path, allowed: Set[str], failure: str, refused: List[List[str]]) -> str:
    files = []
    for rel in sorted(allowed):
        p = copy / rel
        if p.exists():
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[:MAX_LINES]
            files.append("--- %s\n%s" % (rel, "\n".join(lines)))
    parts = ["A refactoring moved Java classes between packages and the build or tests now fail. "
             "Fix the source with the fewest, smallest edits.",
             'Answer with one JSON object and nothing else: {"edits": [{"path": "<file>", '
             '"search": "<exact text, found exactly once>", "replace": "<new text>"}]}',
             "You may edit only these files. Never edit tests, pom.xml, Gradle or META-INF files, "
             "and never add Class.forName, ServiceLoader, MethodHandles or newInstance.",
             "Failure:\n" + failure, "Files:\n" + "\n\n".join(files)]
    if refused:
        parts.append("Your previous edits were refused:\n" + "\n".join("%s: %s" % (p, w) for p, w in refused))
    return "\n\n".join(parts) + "\n"


def repair(model, copy: Path, allowed: Set[str], failure: str, rebuild: Callable[[], Dict[str, Any]],
           budget: int = 5) -> Dict[str, Any]:
    rounds: List[Dict[str, Any]] = []
    edited: List[str] = []
    refused: List[List[str]] = []
    ok = False
    for _ in range(budget):
        try:
            done = model.generate(_prompt(copy, allowed, failure, refused), max_tokens=1500,
                                  temperature=0.2, json_mode=True)
        except Exception as e:                       # endpoint down: stop, the gates still judge
            rounds.append({"why": "model call failed: %s" % str(e)[:200]})
            break
        res = apply_edits(copy, parse_edits(done.text), allowed)
        refused = res["refused"]
        edited += [p for p in res["applied"] if p not in edited]
        built = rebuild()
        ok = bool(built.get("ok"))
        rounds.append({"applied": res["applied"], "refused": refused, "ok": ok,
                       "prompt_tokens": done.prompt_tokens, "completion_tokens": done.completion_tokens})
        if ok:
            break
        log = built.get("log") or ""
        failure = "\n".join(error_summary(log)) or log[-3000:]
    return {"ok": ok, "rounds": rounds, "edited": edited}
