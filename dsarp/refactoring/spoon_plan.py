"""Validate a model's Spoon edit plan against the real source before Spoon ever runs.

Same contract as ai_recipes.py: the model proposes, the source decides. Every edit is
checked against SourceFacts -- the type must exist, the target package must exist, both
must live in the same Maven module -- so a hallucinated FQN is rejected here rather than
becoming a confusing Spoon no-op twenty minutes into a run.

The model's instructions live in .claude/skills/spoon-refactoring/SKILL.md and are loaded
as its system prompt, so the rules it is asked to follow and the rules enforced here are
the same text.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ops the Spoon driver implements. Anything else is rejected without running -- a model
# confidently proposing "extractMethod" is the expected failure, not an exception.
# extractInterface is Dependency Inversion: the consumer package gains an
# interface, the implementation implements it, and the consumer -> impl edge
# disappears. It is the technique the literature leads with for cycles, and the
# reason moveClass alone cleared only 14 of 73 measured candidates.
ALLOWED_OPS = {"moveClass", "extractInterface", "invertEdge"}

SKILL = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "spoon-refactoring" / "SKILL.md"


def system_prompt() -> str:
    """The skill, minus its YAML frontmatter, as the model's system prompt."""
    text = SKILL.read_text(encoding="utf-8") if SKILL.exists() else ""
    return re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S).strip()


@dataclass
class Edit:
    op: str
    type: str
    to_package: str
    interface_name: str = ""
    types: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"op": self.op, "type": self.type, "toPackage": self.to_package}
        if self.interface_name:
            d["interfaceName"] = self.interface_name
        if self.types:
            # invertEdge abstracts EVERY class the consumer names on the far side. One class
            # of twenty-five leaves the package edge exactly where it was, which is what
            # ArrayEntry measured: compiled clean, smell count unchanged.
            d["types"] = list(self.types)
        return d


@dataclass
class Plan:
    smell_type: str = ""
    component: str = ""
    reasoning: str = ""
    edits: List[Edit] = field(default_factory=list)
    declined: List[Dict[str, str]] = field(default_factory=list)
    rejected: List[Dict[str, str]] = field(default_factory=list)
    rejection: str = ""
    raw: str = ""

    @property
    def applicable(self) -> bool:
        return bool(self.edits) and not self.rejection

    def as_dict(self) -> Dict[str, Any]:
        return {"smell_type": self.smell_type, "component": self.component,
                "reasoning": self.reasoning, "edits": [e.as_dict() for e in self.edits],
                "declined": self.declined, "rejected": self.rejected,
                "rejection": self.rejection}


def source_root_of(facts, fqn: str) -> Optional[Path]:
    """The source root a type lives under — the directory its package path hangs off.

    Derived by stripping one directory per package segment, so it works for any layout:
    Maven's src/main/java, Gradle source sets, Android variants, a flat src/. The previous
    version pattern-matched literally on ".../src/main/java" and returned None for every
    repository that does not use it, which silently made this whole agent Maven-only.

    Spoon models one root at a time, so this is also the boundary a move may not cross.
    """
    f = facts.file_for(fqn)
    if not f:
        return None
    pkg = fqn.rsplit(".", 1)[0]
    root = Path(f).resolve().parent
    for _ in pkg.split("."):
        if root.parent == root:            # ran out of path; layout does not match package
            return None
        root = root.parent
    return root


# Files that mark the top of a build module, in the order they are usually nested.
_BUILD_FILES = ("pom.xml", "build.gradle", "build.gradle.kts", "build.xml")


def module_name(root: Optional[Path]) -> str:
    """The build module a source root belongs to — `log4j-api`, not `java`."""
    if root is None:
        return "unknown"
    p = Path(root)
    for parent in [p, *p.parents]:
        if any((parent / b).exists() for b in _BUILD_FILES):
            return parent.name
    return p.name


def package_root(facts, pkg: str) -> Optional[Path]:
    """Cached: enumerating a finding's candidates asks this O(packages^2) times, and it
    walks every class in the package to answer."""
    cache = getattr(facts, "_pkg_root_cache", None)
    if cache is None:
        cache = facts._pkg_root_cache = {}
    if pkg in cache:
        return cache[pkg]
    root = None
    for fqn in facts.classes_in(pkg, production_only=False):
        root = source_root_of(facts, fqn)
        if root:
            break
    cache[pkg] = root
    return root


def parse(raw: str, smell_type: str = "", component: str = "") -> Plan:
    """Pull the JSON object out of a model reply and check its shape."""
    p = Plan(smell_type=smell_type, component=component, raw=raw or "")
    m = re.search(r"\{.*\}", p.raw, re.S)
    if not m:
        p.rejection = "model did not return JSON"
        return p
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        p.rejection = f"model returned invalid JSON: {e}"
        return p
    p.reasoning = str(data.get("reasoning", ""))[:200]
    p.declined = [d for d in (data.get("declined") or []) if isinstance(d, dict)]
    for item in data.get("edits") or []:
        if not isinstance(item, dict):
            continue
        op = str(item.get("op", ""))
        if op not in ALLOWED_OPS:
            p.rejected.append({"edit": json.dumps(item)[:160],
                               "why": f"op '{op}' is not implemented by the Spoon driver"})
            continue
        p.edits.append(Edit(op=op, type=str(item.get("type", "")),
                            to_package=str(item.get("toPackage", ""))))
    return p


def validate(plan: Plan, facts) -> Plan:
    """Drop every edit the source does not support. Reasons are kept, not summarised away."""
    kept: List[Edit] = []
    for e in plan.edits:
        why = _why_not(e, facts)
        if why:
            plan.rejected.append({"edit": json.dumps(e.as_dict()), "why": why})
        else:
            kept.append(e)
    plan.edits = kept
    if not kept and not plan.rejection:
        plan.rejection = ("no edit survived validation"
                          if plan.rejected else "model proposed no edits")
    return plan


def _why_not(e: Edit, facts) -> str:
    if not e.type or not e.to_package:
        return "edit is missing type or toPackage"
    if facts.file_for(e.type) is None:
        return f"{e.type} is not a type in this repository"
    if facts.is_nested(e.type):
        return f"{e.type} is a nested type; only top-level types can be moved"
    from_pkg = e.type.rsplit(".", 1)[0]
    if from_pkg == e.to_package:
        return "source and target package are the same"
    if e.to_package not in facts.packages():
        return f"target package {e.to_package} does not exist in this repository"
    src, dst = source_root_of(facts, e.type), package_root(facts, e.to_package)
    if src is None or dst is None:
        return "could not locate a src/main/java root for the type or the target package"
    if src != dst:
        # Spoon models one root at a time, and a cross-module move needs a new Maven
        # dependency to compile. Refusing is cheaper than discovering it at the build gate.
        # Named by MODULE, not by root: every root is called "java", so "java -> java" was
        # the least informative rejection this could produce.
        return f"cross-module move ({module_name(src)} -> {module_name(dst)}) is not supported"
    if e.op == "extractInterface":
        # The implementation stays exactly where it is, so none of the move blockers apply:
        # they all ask whether this type can LEAVE its package. What extractInterface needs
        # instead -- no constructor calls, no static or field access from the consumer, every
        # signature type visible there -- needs resolved types, so the Spoon precheck decides
        # it and this function only screens the layout.
        return ""
    blockers = (facts.move_blockers(e.type)
                + protected_nested_blockers(facts, e.type)
                + package_private_export_blockers(facts, e.type))
    if blockers:
        return "; ".join(blockers[:3])
    return ""


# A nested type declared `protected` — indented, so not the top-level declaration.
_PROTECTED_NESTED = re.compile(
    r"^[ \t]+protected\s+(?:static\s+|final\s+|abstract\s+)*"
    r"(?:class|interface|enum|record)\s+(\w+)", re.M)


def is_public_type(text: str, simple: str) -> bool:
    """Is the TOP-LEVEL declaration of `simple` public? Top-level means column zero."""
    return bool(re.search(
        rf"^public\s+(?:\w+\s+)*?(?:class|interface|enum|record)\s+{re.escape(simple)}\b",
        text or "", re.M))


def package_private_export_blockers(facts, fqn: str) -> List[str]:
    """This type is package-private and its own package still uses it.

    move_blockers() asks what the moving class needs FROM its package. This is the mirror
    question — what the package needs from the moving class — and nothing was asking it.
    log4j-core failed on exactly this: AbstractAsyncExceptionHandler has no `public`
    modifier, so moving it out of core.async left two siblings unable to see it at all
    ("is not public in ...; cannot be accessed from outside package"). Making it public to
    enable the move would widen an API the authors deliberately kept closed, so the move is
    simply refused.
    """
    pkg, simple = fqn.rsplit(".", 1)[0], fqn.rsplit(".", 1)[-1]
    if is_public_type(facts.text_of(fqn), simple):
        return []
    users = [s for s in facts.classes_in(pkg)
             if s != fqn and re.search(rf"\b{re.escape(simple)}\b", facts.text_of(s) or "")]
    if not users:
        return []
    return [f"{simple} is package-private and {len(users)} class(es) in {pkg} still use it"]


def protected_nested_blockers(facts, fqn: str) -> List[str]:
    """Protected nested types of same-package siblings that this type uses.

    move_blockers() screens package-private members. A `protected` nested type is just as
    unreachable once the user lands in another package, and log4j-core failed on exactly
    that: `LoggerConfig.LevelAndRefs has protected access` after AsyncLoggerConfig moved.
    """
    pkg = fqn.rsplit(".", 1)[0]
    txt = facts.text_of(fqn)
    if not txt:
        return []
    out = []
    for sibling in facts.classes_in(pkg):
        simple = sibling.rsplit(".", 1)[-1]
        if sibling == fqn or simple not in txt:
            continue
        for m in _PROTECTED_NESTED.finditer(facts.text_of(sibling) or ""):
            if re.search(rf"\b{re.escape(simple)}\.{re.escape(m.group(1))}\b", txt):
                out.append(f"uses {simple}.{m.group(1)}, a protected nested type in {pkg}")
    return out


def source_roots_for(plan: Plan, facts) -> List[str]:
    """Roots the driver needs to model — just the ones the surviving edits touch."""
    roots = []
    for e in plan.edits:
        r = source_root_of(facts, e.type)
        if r and str(r) not in roots:
            roots.append(str(r))
    return roots
