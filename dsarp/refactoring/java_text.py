"""Tidy a Java tree after a refactoring backend has rewritten it.

Backend-agnostic on purpose. Spoon and OpenRewrite leave the same three kinds of debris and
each one has already cost a measured run:

  * an import the file no longer uses. Spoon's printer invents these from a lambda's
    INFERRED functional interface - `compoundWords.forEach(word -> ...)` made it print
    `import java.util.function.Consumer;` into a file that never names Consumer. pdfbox
    fails the build on UnusedImports, so Arcan then measured a tree that had not compiled
    and reported 952 -> 2 smells.
  * an import that has become same-package, because the type moved INTO this file's own
    package. Java allows it; checkstyle's RedundantImport does not. This is what failed
    `TreeStatus -> ui` on the OpenRewrite arm while the identical Spoon move compiled.
  * a file whose package declaration no longer matches the directory it sits in.

Deliberately textual and parser-free. Nothing here uses a regex: the first version of the
unused-import check built a word-boundary pattern by interpolation, the escape was eaten
before it reached the file, and the pattern became a literal backspace that matched
nothing - which made every import look unused. Scanning characters has nothing to escape.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_MARKERS = ("src/main/java/", "src/test/java/")


def idents(text: str) -> set:
    """Identifier words in a chunk of Java, so a name can be matched whole.

    `MyListener` must not count as a use of `List`, or nothing is ever pruned.
    """
    out, cur = set(), ""
    for ch in text:
        if ch.isalnum() or ch in "_$":
            cur += ch
        else:
            if cur:
                out.add(cur)
            cur = ""
    if cur:
        out.add(cur)
    return out


def import_fqn(line: str) -> Optional[str]:
    """The type a plain single-type import names, or None for anything else.

    Static imports and wildcard imports return None and are therefore never touched: a
    wildcard's usage cannot be decided from the simple name, and a static import's name is
    a member rather than a type.
    """
    s = line.strip()
    if not s.startswith("import ") or not s.endswith(";"):
        return None
    body = s[len("import "):-1].strip()
    if body.startswith("static ") or body.endswith("*") or " " in body or not body:
        return None
    return body


def package_of(text: str) -> str:
    """The declared package, read before the first import or type declaration."""
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("package ") and s.endswith(";"):
            return s[len("package "):-1].strip()
        if s.startswith("import ") or " class " in f" {s} " or s.startswith("public "):
            break
    return ""


def strip_unused_imports(text: str) -> Tuple[str, List[str]]:
    """Drop single-type imports whose name appears nowhere else in the file.

    A name mentioned anywhere at all keeps its import, javadoc included - erring towards
    keeping an unused import (a warning) over removing a used one (a broken build).
    """
    lines = text.splitlines(keepends=True)
    body = "".join(ln for ln in lines if import_fqn(ln) is None)
    names = idents(body)
    out, dropped = [], []
    for ln in lines:
        fqn = import_fqn(ln)
        if fqn is not None and fqn.rsplit(".", 1)[-1] not in names:
            dropped.append(fqn)
            continue
        out.append(ln)
    return "".join(out), dropped


def drop_same_package_imports(text: str) -> Tuple[str, List[str]]:
    """Remove imports pointing into this file's own package.

    They appear when a type moves INTO the package of a file that already imported it.
    javac accepts them; pdfbox's checkstyle failed the build with four RedundantImport
    errors on code that had compiled perfectly.
    """
    pkg = package_of(text)
    if not pkg:
        return text, []
    out, dropped = [], []
    for ln in text.splitlines(keepends=True):
        fqn = import_fqn(ln)
        if fqn is not None and fqn.rsplit(".", 1)[0] == pkg:
            dropped.append(fqn)
            continue
        out.append(ln)
    return "".join(out), dropped


def source_root_of_file(path) -> Optional[str]:
    """The `src/main/java/` (or test) prefix a file sits under, as a string, or None.

    Layout markers rather than package arithmetic: after a package rename the declared
    package no longer describes the directory, so counting segments off the path would
    resolve the root against the very thing that changed.
    """
    p = str(path).replace("\\", "/")
    for m in _MARKERS:
        i = p.rfind(m)
        if i != -1:
            return p[:i + len(m)]
    return None


def relocate_to_match_package(repo_path, only=None) -> List[str]:
    """Move files whose directory disagrees with their package declaration.

    A backend that rewrites the package statement but leaves the file where it was produces
    source javac rejects outright. Spoon's driver installs moved files itself; OpenRewrite's
    ChangeType is the case this guards.
    """
    moved = []
    for f in _java_files(repo_path, only):
        sp = str(f).replace("\\", "/")
        root = source_root_of_file(f)
        if not root:
            continue
        try:
            pkg = package_of(f.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        if not pkg:
            continue
        want = Path(root + pkg.replace(".", "/")) / f.name
        if want.resolve() == f.resolve():
            continue
        want.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(want))
        moved.append(f"{sp} -> {str(want).replace(chr(92), '/')}")
    return moved


def _java_files(repo_path, only=None):
    """Java sources to act on: every one under `repo_path`, or just `only` when given.

    `only` exists for measurement validity, not speed. An unused import is a dependency
    edge Arcan counts, so pruning imports in files the refactoring never touched would lower
    the smell count on its own and the run would credit the refactoring for it. Restricting
    the tidy to the files the backend actually rewrote keeps the comparison honest.
    """
    root = Path(repo_path).resolve()
    if only is not None:
        out, seen = [], set()
        for f in only:
            q = Path(f)
            # OpenRewrite prints changed files relative to the MAVEN PROCESS cwd, not to the
            # repo it was pointed at. Joining them onto repo_path produced paths that do not
            # exist, every file was silently skipped, and the whole tidy became a no-op -
            # pdfbox still failed on four RedundantImport errors it was meant to remove.
            for cand in ([q] if q.is_absolute() else [root / q, Path.cwd() / q]):
                try:
                    r = cand.resolve()
                except OSError:
                    continue
                if r.suffix != ".java" or not r.is_file():
                    continue
                if root != r and root not in r.parents:
                    continue        # never edit anything outside the repo copy
                if r not in seen:
                    seen.add(r)
                    out.append(r)
                break
        return out
    return [f for f in Path(repo_path).rglob("*.java")
            if "/target/" not in str(f).replace("\\", "/")
            and "/build/" not in str(f).replace("\\", "/")]


def add_origin_imports(repo_path, moves) -> Dict[str, List[str]]:
    """Give a moved file the imports it needs for types it used to sit beside.

    A type in `a.b` naming sibling `Helper` needs no import. Move it to `a.c` and `Helper`
    stops resolving. OpenRewrite's ChangeType rewrites every reference TO the moved type and
    leaves the references FROM it untouched, so pdfbox's TreeStatusPane landed in
    `debugger.ui` still naming `TreeStatus`, which had stayed in `debugger.treestatus`:
    `cannot find symbol` at lines 41 and 116, and the candidate was recorded as a backend
    failure rather than as this missing step. Spoon avoids it by reprinting the moved file
    with real imports; this is the equivalent for every other backend.

    Returns a map of moved file -> imports added, including files located but not changed,
    so the caller knows which files the refactoring touched.
    """
    out: Dict[str, List[str]] = {}
    for old_fqn, new_fqn in moves or []:
        origin_pkg, simple = old_fqn.rsplit(".", 1)
        new_pkg = new_fqn.rsplit(".", 1)[0]
        if origin_pkg == new_pkg:
            continue
        target = None
        for f in Path(repo_path).rglob(simple + ".java"):
            sp = f.as_posix()
            if "/target/" in sp or "/build/" in sp:
                continue
            try:
                if package_of(f.read_text(encoding="utf-8", errors="ignore")) == new_pkg:
                    target = f
                    break
            except OSError:
                continue
        if target is None:
            continue
        root = source_root_of_file(target)
        if not root:
            continue
        origin_dir = Path(root + origin_pkg.replace(".", "/"))
        out[target.as_posix()] = []
        if not origin_dir.is_dir():
            continue
        left_behind = {q.stem for q in origin_dir.glob("*.java")} - {simple, "package-info"}
        txt = target.read_text(encoding="utf-8", errors="ignore")
        body = "".join(ln for ln in txt.splitlines(keepends=True) if import_fqn(ln) is None)
        used = idents(body)
        need = sorted(n for n in left_behind
                      if n in used and (origin_pkg + "." + n) not in txt)
        if not need:
            continue
        lines, new_lines, done = txt.splitlines(keepends=True), [], False
        for ln in lines:
            new_lines.append(ln)
            s = ln.strip()
            if not done and s.startswith("package ") and s.endswith(";"):
                for n in need:
                    new_lines.append("import " + origin_pkg + "." + n + ";" + chr(10))
                done = True
        target.write_text("".join(new_lines), encoding="utf-8")
        out[target.as_posix()] = need
    return out


def tidy_tree(repo_path, relocate: bool = True, only=None, moves=None) -> Dict[str, object]:
    """Apply every cleanup. Safe to run when there is nothing to do.

    Pass `only` with the files the backend reported changing; see `_java_files`. Pass `moves`
    as (old_fqn, new_fqn) pairs so a moved file can regain the imports it needs for the
    types it left behind - the moved file itself is usually ABSENT from the backend's list
    of changed files, so it has to be added to the set explicitly.
    """
    pruned: Dict[str, List[str]] = {}
    redundant: Dict[str, List[str]] = {}
    origin_imports = add_origin_imports(repo_path, moves)
    if only is not None:
        only = list(only) + [f for f in origin_imports if f not in set(only)]
    moved = relocate_to_match_package(repo_path, only) if relocate else []
    for f in _java_files(repo_path, only):
        sp = str(f).replace("\\", "/")
        try:
            original = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        txt, same = drop_same_package_imports(original)
        txt, unused = strip_unused_imports(txt)
        if txt != original:
            f.write_text(txt, encoding="utf-8")
            if same:
                redundant[sp] = same
            if unused:
                pruned[sp] = unused
    return {"files_relocated": moved,
            "origin_imports_added": {k: v for k, v in origin_imports.items() if v},
            "same_package_imports_dropped": redundant,
            "unused_imports_dropped": pruned}


_WORD_RE = None


def _word(name: str):
    """A compiled whole-word matcher for a Java identifier."""
    global _WORD_RE
    import re as _re
    return _re.compile(r"(?<![A-Za-z0-9_$.])" + _re.escape(name) + r"(?![A-Za-z0-9_$])")


def add_implements(text: str, class_simple: str, iface_fqn: str):
    """Add `implements <Iface>` to a top-level class declaration, in place.

    Textual, so the file keeps its original formatting. Spoon's default printer reformats
    every compilation unit it models, and pdfbox rejected two otherwise-correct candidates on
    `Line is longer than 200 characters` with no javac error at all: the transformation was
    right and the reflow failed the style gate. Only the newly created interface is taken
    from the printer, because it has no original formatting to lose.
    """
    import re as _re
    iface = iface_fqn.rsplit(".", 1)[-1]
    m = _re.search(r"\b(?:final\s+|abstract\s+|public\s+|strictfp\s+)*class\s+"
                   + _re.escape(class_simple) + r"\b", text)
    if not m:
        return text, False
    # Walk to the class body's opening brace, ignoring braces inside annotations or generics.
    i, depth = m.end(), 0
    while i < len(text):
        c = text[i]
        if c == "<":
            depth += 1
        elif c == ">":
            depth -= 1
        elif c == "{" and depth <= 0:
            break
        i += 1
    if i >= len(text):
        return text, False
    head = text[m.end():i]
    if _word(iface).search(head):
        return text, True                      # already implements it
    if _re.search(r"\bimplements\b", head):
        j = i
        while j > m.end() and text[j - 1] in " \t\r\n":
            j -= 1
        new = text[:j] + ", " + iface + text[j:]
    else:
        j = i
        while j > m.end() and text[j - 1] in " \t\r\n":
            j -= 1
        new = text[:j] + " implements " + iface + text[j:]
    return _ensure_import(new, iface_fqn), True


def _ensure_import(text: str, fqn: str) -> str:
    """Add a single-type import unless the file is already in that package or has it."""
    if package_of(text) == fqn.rsplit(".", 1)[0]:
        return text
    line = "import " + fqn + ";"
    if line in text:
        return text
    out, done = [], False
    for ln in text.splitlines(keepends=True):
        out.append(ln)
        s = ln.strip()
        if not done and s.startswith("package ") and s.endswith(";"):
            out.append(line + chr(10))
            done = True
    return "".join(out) if done else line + chr(10) + text


def _declaration_use(name: str):
    """Matches a type name used as a DECLARED TYPE, not in the places an interface cannot go.

    A blunt whole-word swap was wrong in a way the compiler caught immediately: the constraint
    solver said the declaration `Meter meter` could become `MeterApi meter`, the textual pass
    also rewrote the initialiser, and javac answered "MeterApi is abstract; cannot be
    instantiated". Changing a declaration's type says nothing about what is assigned into it.

    So these are left alone:
        new X(...)      the constructor still names the class
        X.something     static access and X.class
        X::something    method and constructor references
    """
    import re as _re
    return _re.compile(r"(?<!new )(?<![A-Za-z0-9_$.])" + _re.escape(name)
                       + r"(?![A-Za-z0-9_$.:])")


def retarget_type(text: str, old_fqn: str, new_fqn: str) -> str:
    """Point a consumer file's DECLARATIONS at the extracted interface.

    The driver decides which declarations may move, by type constraints over the resolved
    model. This applies that decision to the original text rather than taking the printer's
    reformatted copy, because the printer reflows whole files and pdfbox rejects the result on
    line length. The patterns here mirror what the solver allows; the compile gate is still
    what confirms it.
    """
    old_simple = old_fqn.rsplit(".", 1)[-1]
    new_simple = new_fqn.rsplit(".", 1)[-1]

    # Imports are rewritten by their own rules, never by the declaration substitution. Letting
    # the substitution near them turned `import com.x.engine.Meter;` into
    # `import com.x.app.MeterApi;` -- the old import was transformed rather than kept, so the
    # surviving `new Meter()` lost its declaration and javac said "cannot find symbol".
    lines = text.splitlines(keepends=True)
    imports = [i for i, ln in enumerate(lines) if import_fqn(ln) is not None]
    body_idx = [i for i in range(len(lines)) if i not in set(imports)]
    for i in body_idx:
        lines[i] = _declaration_use(old_fqn).sub(new_fqn, lines[i])
        lines[i] = _declaration_use(old_simple).sub(new_simple, lines[i])

    body = "".join(lines[i] for i in body_idx)
    names = idents(body)
    # Keep the old import only while something still names the class -- a retargeted
    # declaration routinely keeps its initialiser, and `MeterApi meter = new Meter()` needs it.
    keep_old = old_simple in names
    out = []
    for i, ln in enumerate(lines):
        fqn = import_fqn(ln)
        if fqn == old_fqn and not keep_old:
            continue
        out.append(ln)
    text = "".join(out)
    if new_simple in names:
        text = _ensure_import(text, new_fqn)
    return text
