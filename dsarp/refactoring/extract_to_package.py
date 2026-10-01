"""Extract the members that carry a package edge into a new class in a NEW package.

This is the operation two expert refactorings in the Arcelli Fontana replication package both
perform, and the one DSARP did not have. In their words, for Jackrabbit: "Create a new utility
class ... in a newly created 'util' package. Move the functionality that is causing dependencies
... to this new class." Commons Compress is the same shape -- an `archivers.factory` package
appeared, and `archivers -> archivers.ar/arj/cpio/...` became `archivers.factory ->
archivers.ar/...`.

It is a composite: create a package, create a class in it, move the members that reach across
the edge, let the references invert. Moving methods alone does not do this -- measured on
SWE-Refactor's cross-package method moves, 0 of 5 removed a package edge, because a method move
leaves the class, and therefore the package, where it was.

What is reused, and why only this subset. `extract_class` already extracts PUBLIC STATIC methods
and nothing else, because a static method cannot touch `this`, so relocating it is
behaviour-preserving without type attribution or a judgement about which members belong
together. That restraint is kept. What changes is the destination: `extract_class` writes the new
type into the source's own directory and adds no import, which is correct for shrinking a God
Class and useless for architecture, since a type in the same package moves no edge.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .extract_class import (_cut_methods, _find_file, _repoint, static_methods,
                            uses_instance_state, uses_non_public_members)
from .strategies import SourceFacts

# The new package's leaf name. The experts used `factory` and `util`; `support` says what the
# class is for without claiming a pattern the code may not implement. Several extracted classes
# can share it, exactly as archivers.factory holds several.
LEAF = "support"


def methods_reaching(facts: SourceFacts, fqn: str, target_pkg: str,
                     limit: int = 24) -> List[str]:
    """Extractable static methods of `fqn` whose bodies name a type from `target_pkg`.

    These are the members that carry the edge. Extracting the class's other static methods as
    well would move code for no structural reason.
    """
    text = facts.text_of(fqn) or ""
    if not text:
        return []
    names = {c.rsplit(".", 1)[-1] for c in facts.classes_in(target_pkg)}
    if not names:
        return []
    out: List[str] = []
    for m in static_methods(facts, fqn):
        if uses_instance_state(facts, fqn, m) or uses_non_public_members(facts, fqn, m):
            continue
        if _overloaded(text, m):
            # _cut_methods takes one declaration per name. With an overload, the other
            # declaration stays behind and the unqualified-call rewrite turns it into
            # `public static boolean Support.isDate(` -- a syntax error. Measured on
            # commons-validator's GenericValidator.isDate, which has two overloads.
            # extract_class guards the case where NO declaration was cut; this is the case
            # where one was and another remains.
            continue
        bodies, _ = _cut_methods(text, [m])
        if not bodies:
            continue
        body = bodies[0]
        if any(re.search(r"\b%s\b" % re.escape(n), body) for n in names):
            out.append(m)
            if len(out) >= limit:
                break
    return out


def plan(facts: SourceFacts, edge: Dict[str, Any], min_methods: int = 2) -> Optional[Dict[str, Any]]:
    """A composite extraction aimed at one package edge, or None when it does not apply.

    `edge` is a snapshot edge: from, to, and the class pairs that carry it. Only the consumer
    side is considered -- the members doing the reaching live there.
    """
    frm, to = edge["from"], edge["to"]
    carriers = sorted({p.split(" -> ")[0].split("$")[0]
                       for p in (edge.get("carriers") or []) if " -> " in p})
    for cls in carriers:
        if not facts.file_for(cls):
            continue
        methods = methods_reaching(facts, cls, to)
        if len(methods) < min_methods:
            continue
        simple = cls.rsplit(".", 1)[-1]
        new_pkg = "%s.%s" % (frm, LEAF)
        target = "%s.%sSupport" % (new_pkg, simple)
        if facts.file_for(target):
            continue
        return {
            "op": "extractToNewPackage",
            "edge": "%s -> %s" % (frm, to),
            "from_package": frm, "to_package": to,
            "source_class": cls, "target_class": target, "new_package": new_pkg,
            "methods": methods,
            "carrier_classes": carriers,
            # Stated before anything is applied, and deliberately conditional: the edge goes
            # only if these methods were the whole reason this class reached across it, and
            # only if no OTHER class in the package reaches across it too. The oracle decides.
            "success_criterion": (
                "the bytecode edge %s -> %s no longer exists, which requires that these %d "
                "method(s) were the only path from %s to %s and that no other class in %s "
                "reaches it" % (frm, to, len(methods), cls.rsplit(".", 1)[-1], to, frm)),
            "sole_carrier": len(carriers) == 1,
        }
    return None


def apply(repo_path: Path, candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Create the package and class, move the methods, repoint callers, add imports.

    Differs from extract_class.apply_extractions in the two places that assume one package:
    the file is written under the new package's directory, and every file that now calls the
    extracted methods gets an import, because the type is no longer a package-mate.
    """
    repo_path = Path(repo_path)
    src_fqn = candidate["source_class"]
    target = candidate["target_class"]
    src = _find_file(repo_path, src_fqn)
    if src is None:
        return {"ok": False, "why": "source file for %s not found" % src_fqn}
    text = src.read_text(encoding="utf-8")
    bodies, remaining = _cut_methods(text, candidate["methods"])
    if not bodies:
        return {"ok": False, "why": "none of the planned methods could be cut cleanly"}

    new_pkg, simple = target.rsplit(".", 1)
    src_simple = src_fqn.rsplit(".", 1)[-1]
    # The source root is the directory the old package resolves under, so the new package's
    # directory hangs off the same root rather than off the file's own folder.
    old_rel = src_fqn.rsplit(".", 1)[0].replace(".", "/")
    root = Path(str(src.parent).replace("\\", "/")[:-len(old_rel)] if
                str(src.parent).replace("\\", "/").endswith(old_rel) else str(src.parent))
    out_dir = root / new_pkg.replace(".", "/")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / ("%s.java" % simple)
    if out.exists():
        return {"ok": False, "why": "%s already exists" % target}

    imports = "\n".join(re.findall(r"^import [^\n]+;", text, re.M))
    # The extracted bodies referenced the source's package-mates without an import, because
    # they were in the same package. From the new package they need one.
    siblings = sorted({c for c in re.findall(r"\b([A-Z][A-Za-z0-9_]*)\b", "\n".join(bodies))})
    sib_imports = []
    for name in siblings:
        fq = "%s.%s" % (src_fqn.rsplit(".", 1)[0], name)
        if name != src_simple and _find_file(repo_path, fq):
            sib_imports.append("import %s;" % fq)
    header = "package %s;\n\n" % new_pkg
    if imports or sib_imports:
        header += "\n".join([imports] + sorted(set(sib_imports))).strip() + "\n\n"
    out.write_text(
        header
        + "/** Static helpers extracted by DSARP from %s, so that %s no longer reaches\n"
          "  * into %s. Static methods cannot reach instance state, so moving them\n"
          "  * preserves behaviour. */\n" % (src_simple, candidate["from_package"],
                                             candidate["to_package"])
        + "public final class %s {\n\n    private %s() {\n    }\n\n" % (simple, simple)
        + "\n\n".join(bodies) + "\n}\n", encoding="utf-8")

    extracted = [m for m in candidate["methods"]
                 if re.search(r"\b%s\s*\(" % re.escape(m), "\n".join(bodies))]
    src.write_text(_add_import(_repoint(remaining, src_simple, simple, extracted,
                                        own_file=True), target),
                   encoding="utf-8")
    touched = 1
    for other in Path(repo_path).rglob("*.java"):
        if other in (src, out):
            continue
        try:
            t = other.read_text(encoding="utf-8")
        except OSError:
            continue
        if src_simple not in t:
            continue
        nt = _repoint(t, src_simple, simple, extracted, own_file=False)
        if nt != t:
            other.write_text(_add_import(nt, target), encoding="utf-8")
            touched += 1
    return {"ok": True, "created": target, "methods_moved": len(bodies),
            "files_touched": touched, "new_package": new_pkg}


def _add_import(text: str, fqn: str) -> str:
    """Import `fqn` after the package declaration, unless it is already there."""
    if re.search(r"^import %s;" % re.escape(fqn), text, re.M):
        return text
    m = re.search(r"^package [^\n]+;\n", text, re.M)
    if not m:
        return text
    return text[:m.end()] + "\nimport %s;\n" % fqn + text[m.end():]


def _overloaded(text: str, method: str) -> bool:
    """Is this static method declared more than once in the class?

    Counted on the declaration shape _cut_methods matches, so the answer is about the same
    declarations the surgery will act on.
    """
    pat = r"^[ \t]{1,8}public\s+static\b[^;{\n]*\b%s\s*\(" % re.escape(method)
    return len(re.findall(pat, text, re.M)) > 1
