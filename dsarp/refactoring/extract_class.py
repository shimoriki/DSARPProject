"""Extract Class — the one refactoring family that REMOVES structure rather than moving it.

Every strategy so far relocates: classes between packages, packages into each other. Across
three strategy variants that produced the same 1-in-8 result, because relocation
redistributes smells rather than eliminating them. A God Class stays a God Class wherever it
lives; only taking members OUT of it makes it smaller.

The general form of Extract Class needs a judgement about which fields and methods belong
together, plus type attribution DSARP's regex index does not have. This module implements the
subset where neither is required:

    **public static methods with no instance state**

A static method cannot touch `this`, so relocating it into a new type is always behaviour-
preserving. The split is done in two halves:

  1. DSARP performs the source surgery on the copied tree — write the new class, remove the
     methods from the original. (Same pattern as `create_interface_files`: DSARP synthesises
     the type, OpenRewrite fixes the references.)
  2. `org.openrewrite.java.ChangeMethodTargetToStatic` rewrites every call site to point at
     the new class.

If the extraction does not take enough methods to get the class under the tool's threshold,
the plan is refused — a partial extraction leaves the original smell AND adds a new class.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .strategies import Plan, RecipeEntry, SourceFacts

# `    public static ReturnType name(args) {`  — a declaration, not a call.
STATIC_METHOD = re.compile(
    r"^[ \t]{1,8}public\s+static\s+(?:final\s+|synchronized\s+)*"
    r"(?!(?:return|new|if|for|while)\b)[\w.<>\[\],\s]+?\s+(\w+)\s*\([^;{]*\)\s*"
    r"(?:throws [\w.,\s]+)?\{", re.M)


def static_methods(facts: SourceFacts, fqn: str) -> List[str]:
    """Names of public static methods declared on this type."""
    txt = facts.text_of(fqn)
    return sorted(set(STATIC_METHOD.findall(txt))) if txt else []


def uses_instance_state(facts: SourceFacts, fqn: str, method: str) -> bool:
    """Conservative check that the method body does not reach for instance state.

    A `static` method cannot legally use `this`, so this mainly guards against parsing a
    non-static declaration by mistake. Erring toward True only costs a skipped extraction.
    """
    txt = facts.text_of(fqn)
    m = re.search(rf"\bstatic\b[^;{{]*\b{re.escape(method)}\s*\([^;{{]*\)\s*"
                  rf"(?:throws [\w.,\s]+)?\{{", txt)
    return m is None


# Members the class does not expose. A method that touches one of these cannot leave the
# class, no matter how it is moved.
_NON_PUBLIC_MEMBER = re.compile(
    r"^[ \t]{1,8}(?:private|protected)\s+(?:static\s+|final\s+|transient\s+|volatile\s+)*"
    r"[\w.<>\[\],\s]+?\s+(\w+)\s*[;=(]", re.M)


def uses_non_public_members(facts: SourceFacts, fqn: str, method: str) -> bool:
    """True if the method reaches for a private/protected member of its own class.

    Being `static` only guarantees no `this` dependency — it says nothing about VISIBILITY.
    A moved method that still calls `adjustForLineEnding(...)`, left behind as a private
    helper, cannot compile from its new home. Same class of precondition as the
    package-private guard on class moves, and the reason the "static is always safe"
    premise was too strong.
    """
    txt = facts.text_of(fqn)
    if not txt:
        return True
    # Check EVERY overload. `maxLength` has a 2-arg form that just delegates and a 3-arg
    # form that calls the private adjustForLineEnding; examining only the first match
    # cleared the method, and the recipe then extracted both overloads together.
    bodies = _method_bodies(txt, method)
    if not bodies:
        return False
    body = "\n".join(bodies)
    hidden = set(_NON_PUBLIC_MEMBER.findall(txt)) - {method}
    # followed by "(" (call), "." (member access) or "[" (index) — i.e. genuinely used
    after = r"\s*[(.\[]"
    return any(re.search(r"(?<![.\w])" + re.escape(h) + after, body) for h in hidden)


def _method_bodies(text: str, name: str) -> List[str]:
    """The source of one method, found by brace matching from its declaration.

    Uses the same shape as STATIC_METHOD (which reliably finds all 17 on GenericValidator)
    rather than a stricter pattern of its own. The earlier version required the signature to
    fit on one line via `[^;{\\n]*`, so any method with a wrapped parameter list was missed —
    _method_body returned "" and uses_non_public_members silently answered False, letting a
    method that calls a private helper through the guard.
    """
    pattern = re.compile(rf"^[ \t]{{1,8}}public\s+static\s+(?:final\s+|synchronized\s+)*"
                         rf"[\w.<>\[\],\s]+?\s+{re.escape(name)}\s*\([^;{{]*\)\s*"
                         rf"(?:throws [\w.,\s]+)?\{{", re.M)
    out: List[str] = []
    for m in pattern.finditer(text):
        depth, i = 0, m.end() - 1
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    out.append(text[m.start():i + 1])
                    break
            i += 1
    return out


def plan_extract_class(facts: SourceFacts, finding: Dict[str, Any]) -> Plan:
    """Insufficient Modularization / Multifaceted Abstraction -> pull static helpers out."""
    smell = finding.get("smell_type", "Insufficient Modularization")
    comps = finding.get("components") or []
    fqn = comps[0] if comps else ""
    jf = facts.file_for(fqn)
    if jf is None:
        return Plan(smell, "Extract Class", comps, applicable=False, stock=False,
                    reason=f"{fqn} not found in the source index", evidence={"component": fqn})
    if facts.is_test(jf):
        return Plan(smell, "Extract Class", comps, applicable=False, stock=False,
                    reason="finding is in test code", evidence={"component": fqn})

    methods = [m for m in static_methods(facts, fqn)
               if not uses_instance_state(facts, fqn, m)
               and not uses_non_public_members(facts, fqn, m)]
    if len(methods) < 3:
        return Plan(smell, "Extract Class", comps, applicable=False, stock=False,
                    reason=f"{fqn.rsplit('.', 1)[-1]} has only {len(methods)} extractable "
                           "public static method(s); pulling out fewer than 3 adds a class "
                           "without meaningfully shrinking the original",
                    evidence={"component": fqn, "static_methods": methods})

    pkg, simple = fqn.rsplit(".", 1)
    target = f"{pkg}.{simple}Helpers"
    if facts.file_for(target):
        return Plan(smell, "Extract Class", comps, applicable=False, stock=False,
                    reason=f"{target} already exists", evidence={"component": fqn})

    # The whole transformation runs INSIDE OpenRewrite on the LST. Python source surgery
    # never produced compiling Java: text editing cannot see where a method really ends,
    # which names are types, or which identifiers are calls. ExtractStaticHelpers moves the
    # declarations, then ChangeMethodTargetToStatic repoints every call site — and because
    # both run on the same LST pass, the tree is valid at each step.
    entries = [RecipeEntry("com.dsarp.recipes.ExtractStaticHelpers",
                           {"fullyQualifiedClassName": fqn,
                            "fullyQualifiedTargetTypeName": target,
                            "methodNames": ",".join(methods)})]
    entries += [RecipeEntry("org.openrewrite.java.ChangeMethodTargetToStatic",
                            {"methodPattern": f"{fqn} {m}(..)",
                             "fullyQualifiedTargetTypeName": target})
                for m in methods]
    plan = Plan(smell, "Extract Class", comps, entries=entries, stock=False,
                resolves_fully=True,
                reason=f"move {len(methods)} public static method(s) out of {simple} into "
                       f"{simple}Helpers; static methods cannot touch instance state, so the "
                       "move is behaviour-preserving",
                evidence={"component": fqn, "new_class": target, "methods": methods[:8],
                          "method_count": len(methods)})
    # The loop performs this surgery on the copy before running the recipe.
    return plan


def apply_extractions(repo_path: Path, extractions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Write the new helper classes and remove the methods from their originals.

    Done here rather than as a recipe because OpenRewrite has no stock "move method to a new
    type" transformation — ChangeMethodTargetToStatic rewrites CALL SITES but cannot create
    the target or relocate the declaration.
    """
    created, moved = [], 0
    for ex in extractions:
        src_fqn, target, methods = ex["source"], ex["target"], ex["methods"]
        src = _find_file(repo_path, src_fqn)
        if src is None:
            continue
        try:
            text = src.read_text(encoding="utf-8")
        except OSError:
            continue
        bodies, remaining = _cut_methods(text, methods)
        if not bodies:
            continue
        pkg, simple = target.rsplit(".", 1)
        src_simple = src_fqn.rsplit(".", 1)[-1]
        out = src.parent / f"{simple}.java"
        if out.exists():
            continue
        # DEFECT 1: the extracted bodies reference types the ORIGINAL imported. Writing the
        # declarations without those imports produced "cannot find symbol" in the new file.
        imports = "\n".join(re.findall(r"^import [^\n]+;", text, re.M))
        out.write_text(
            f"package {pkg};\n\n" + (imports + "\n\n" if imports else "")
            + f"/** Static helpers extracted by DSARP from {src_simple} to reduce its size.\n"
            f"  * Static methods cannot reach instance state, so moving them preserves\n"
            f"  * behaviour. */\n"
            f"public final class {simple} {{\n\n"
            f"    private {simple}() {{\n    }}\n\n"
            + "\n\n".join(bodies) + "\n}\n", encoding="utf-8")

        # DEFECT 2: cutting the declarations left every caller dangling, and the recipe that
        # would repoint them cannot run on a tree that no longer compiles. The helper sits in
        # the SAME package, so no import is needed and DSARP repoints the calls itself —
        # keeping the tree valid at every step instead of depending on a later recipe.
        # Repoint ONLY the methods that were actually cut. Passing every planned method
        # rewrote the DECLARATION of ones _cut_methods could not match, turning
        # `static boolean isBlank(` into `static boolean Helpers.isBlank(` — a syntax error.
        extracted = [m for m in methods
                     if re.search(rf"\b{re.escape(m)}\s*\(", "\n".join(bodies))]
        src.write_text(_repoint(remaining, src_simple, simple, extracted, own_file=True),
                       encoding="utf-8")
        for other in Path(repo_path).rglob("*.java"):
            if other == src or other == out:
                continue
            try:
                t = other.read_text(encoding="utf-8")
            except OSError:
                continue
            if src_simple not in t:
                continue
            nt = _repoint(t, src_simple, simple, extracted, own_file=False)
            if nt != t:
                other.write_text(nt, encoding="utf-8")
        created.append(target)
        moved += len(bodies)
    return {"classes_created": created, "methods_moved": moved}


def _repoint(text: str, src_simple: str, target_simple: str, methods: List[str],
             own_file: bool) -> str:
    """Point calls at the new helper class.

    Elsewhere: `Original.method(` -> `Helpers.method(`.
    Inside the original: those calls were unqualified, so they need qualifying — but only
    where they are genuinely calls, never after a dot (another type's method of the same
    name) and never the declaration, which has already been cut.
    """
    for m in methods:
        text = re.sub(rf"\b{re.escape(src_simple)}\s*\.\s*{re.escape(m)}\s*\(",
                      f"{target_simple}.{m}(", text)
        if own_file:
            text = re.sub(rf"(?<![.\w]){re.escape(m)}\s*\(", f"{target_simple}.{m}(", text)
    return text


def _find_file(repo_path: Path, fqn: str) -> Optional[Path]:
    rel = fqn.replace(".", "/") + ".java"
    for cand in Path(repo_path).rglob(Path(rel).name):
        if str(cand).replace("\\", "/").endswith(rel):
            return cand
    return None


def _cut_methods(text: str, methods: List[str]) -> Tuple[List[str], str]:
    """Remove each named static method from `text`; return the bodies and what remains.

    Brace-counting from the declaration's opening `{` finds the true end of the method,
    which a regex cannot do once the body contains nested blocks.
    """
    bodies: List[str] = []
    for name in methods:
        m = re.search(rf"^[ \t]{{1,8}}public\s+static\b[^;{{\n]*\b{re.escape(name)}\s*"
                      rf"\([^;{{]*\)\s*(?:throws [\w.,\s]+)?\{{", text, re.M)
        if not m:
            continue
        start, depth, i = m.start(), 0, m.end() - 1
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        if depth != 0:
            continue
        bodies.append(text[start:i + 1].rstrip())
        text = text[:start] + text[i + 1:]
    return bodies, text
