"""Leave a deprecated facade at a moved public class's old name, so callers outside the repo
keep compiling and linking.

Every accepted cycle repair so far broke the public API, because a move renames the type for
everyone who depends on the library. A facade keeps the old name and delegates to the new one:

  * subclass   - `old.X extends new.X`, constructors re-declared. Static methods and fields
                 resolve through the superclass, in source and in the JVM's own lookup.
  * interface  - `old.X extends new.X`, statics re-declared because interfaces do not
                 inherit them.
  * statics    - a final or non-instantiable class: static methods and constants only, and
                 the instance API is reported as not covered.

Read from `javap -public` on the BASELINE classes, so the signatures are the compiler's own and
nothing is parsed out of source. A facade is a new edge from the old package to the new one,
and Arcan counts it: if that edge closes the cycle again, the run says so.

What no facade fixes, and japicmp still reports: other methods whose signatures named the moved
type, nested types (`old.X$Inner` is gone in bytecode), and methods returning the moved type
itself. Library code also still builds `new.X` objects, so a caller casting them to `old.X` fails
at run time, which no API checker sees.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .java_text import read_source, write_source

_SKIP = ("java.lang.Enum<", "java.lang.Record", "java.lang.annotation.Annotation")


def _split_top(s: str) -> List[str]:
    """Split on commas outside angle brackets."""
    out, depth, cur = [], 0, ""
    for c in s:
        depth += c == "<"
        depth -= c == ">"
        if c == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += c
    return out + [cur.strip()] if cur.strip() else out


def _type_params(after_name: str) -> Tuple[str, str]:
    """`<K, V extends X<V>>` -> (the declaration, `<K, V>`), or two empty strings."""
    if not after_name.startswith("<"):
        return "", ""
    depth = 0
    for i, c in enumerate(after_name):
        depth += (c == "<") - (c == ">")
        if depth == 0:
            decl = after_name[:i + 1]
            names = [p.split()[0] for p in _split_top(decl[1:-1])]
            return decl, "<%s>" % ", ".join(names)
    return "", ""


_MEMBER = re.compile(r"^\s*(public|protected)\s+(static\s+)?(final\s+)?(?:(<.*?>)\s+)?"
                     r"(?:(\S+)\s+)?([\w.$]+)(?:\((.*)\))?(\s+throws\s+[^;]+)?;\s*$")


def _params(raw: str) -> Tuple[str, str]:
    types = _split_top(raw) if raw.strip() else []
    return (", ".join("%s p%d" % (t, i) for i, t in enumerate(types)),
            ", ".join("p%d" % i for i in range(len(types))))


def facade_source(header: str, old_fqn: str, new_fqn: str, javap: str) -> Tuple[Optional[str], str]:
    """Java source for the facade, or None, and the kind made or the reason none was."""
    javap = javap.replace("$", ".")
    head = next((l for l in javap.splitlines() if old_fqn in l and l.rstrip().endswith("{")), "")
    if not head.startswith("public "):
        return None, "not public, so not API"
    if any(s in head for s in _SKIP):
        return None, "enum, record or annotation: cannot be extended"
    pkg, simple = old_fqn.rsplit(".", 1)
    decl, names = _type_params(head.split(old_fqn, 1)[1])
    is_iface = " interface " in head
    # A delegated static names the moved type and its nested types by their new names: the
    # facade declares no `old.X.Inner`, and `new.X.m` returns `new.X`, not `old.X`.
    retype = lambda s: re.sub(r"(?<![\w.])%s\b" % re.escape(old_fqn), new_fqn, s) if s else s
    statics, ctors = [], []
    for line in javap.splitlines()[1:]:
        m = _MEMBER.match(line)
        if not m:
            continue
        access, static, final, tps, typ, name, params, throws = m.groups()
        tps, throws = (tps + " ") if tps else "", throws or ""
        if params is not None and name == old_fqn:
            p, args = _params(params)
            ctors.append("    %s %s%s(%s)%s {\n        super(%s);\n    }\n"
                         % (access, tps, simple, p, throws, args))
        elif static and params is not None:
            typ, (p, args) = retype(typ), _params(retype(params))
            ret = "" if typ == "void" else "return "
            statics.append("    %s static %s%s %s(%s)%s {\n        %s%s.%s(%s);\n    }\n"
                           % (access, tps, typ, name, p, throws, ret, new_fqn, name, args))
        elif static and final:
            statics.append("    %s static final %s %s = %s.%s;\n" % (access, retype(typ), name, new_fqn, name))
    doc = "/**\n * @deprecated moved to {@link %s}; this name delegates to it.\n */\n@Deprecated\n" % new_fqn
    if is_iface:
        kind, body = "interface", "public interface %s%s extends %s%s {\n%s}\n" % (
            simple, decl, new_fqn, names, "".join(statics))
    elif " final " not in head and ctors:
        abstract = "abstract " if " abstract " in head else ""
        kind, body = "subclass", "public %sclass %s%s extends %s%s {\n%s}\n" % (
            abstract, simple, decl, new_fqn, names, "\n".join(ctors))
    elif statics:
        kind = "statics" + ("; instance API not covered" if ctors else "")
        body = "public final class %s {\n    private %s() {\n    }\n\n%s}\n" % (
            simple, simple, "\n".join(statics))
    else:
        return None, "final with no static members to delegate"
    return "%spackage %s;\n\n%s%s" % (header, pkg, doc, body), kind


def _javap(classes: Path, fqn: str) -> str:
    from ..tools.spoon_runner import java_exe
    java = java_exe() or "java"
    javap = str(Path(java).with_name("javap.exe" if java.endswith(".exe") else "javap"))
    p = subprocess.run([javap, "-public", "-cp", str(classes), fqn],
                       capture_output=True, text=True, timeout=120)
    return p.stdout if p.returncode == 0 else ""


def add_facades(baseline: Path, copy: Path, moves: List[List[str]]) -> List[Dict[str, Any]]:
    """Write a facade into `copy` at each moved class's old path, from `baseline`'s classes."""
    from ..tools.spoon_runner import module_of
    from .spoon_plan import source_root_of
    from .strategies import SourceFacts

    facts, made = SourceFacts(baseline), []
    for cls, dest in moves:
        new_fqn = "%s.%s" % (dest, cls.rsplit(".", 1)[1])
        src, root = facts.file_for(cls), source_root_of(facts, cls)
        if not src or not root:
            made.append({"type": cls, "kind": None, "why": "no baseline source"})
            continue
        javap = _javap(module_of(Path(root)) / "target" / "classes", cls)
        text = read_source(src)
        pkg_at = re.search(r"^\s*package\s", text, re.M)
        java, kind = (facade_source(text[:pkg_at.start()] if pkg_at else "", cls, new_fqn, javap)
                      if javap else (None, "javap failed"))
        if java:
            write_source(Path(copy) / Path(src).relative_to(baseline), java)
        made.append({"type": cls, "kind": kind if java else None, "why": None if java else kind})
    return made
