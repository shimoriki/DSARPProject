"""Hierarchy-smell strategies — the refactorings that need a NEW supertype.

These are the cases relocation cannot reach. Both use DSARP's `IntroduceSupertype` recipe,
which wraps rewrite-java's `ImplementInterface` visitor (not usable declaratively on its own)
and pairs it with an interface file DSARP writes before the run.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from .params import RefactoringParams
from .strategies import Plan, RecipeEntry, SourceFacts, _name_stem

PARAMS = RefactoringParams.load()


def _sibling_group(facts: SourceFacts, fqn: str) -> List[str]:
    """Classes in the same package sharing this one's name stem (they play the same role)."""
    pkg = fqn.rsplit(".", 1)[0]
    stem = _name_stem(fqn.rsplit(".", 1)[-1])
    if not stem:
        return []
    out = []
    for other in facts.classes_in(pkg):
        simple = other.rsplit(".", 1)[-1]
        if _name_stem(simple) != stem:
            continue
        txt = facts.text_of(other)
        # only concrete, non-generic classes: an interface cannot be added to an enum/record,
        # and generic classes would need matching type parameters on the supertype
        if not re.search(rf"\bclass\s+{re.escape(simple)}\b", txt):
            continue
        if re.search(rf"\bclass\s+{re.escape(simple)}\s*<", txt):
            continue
        out.append(other)
    return sorted(out)


def plan_introduce_supertype(facts: SourceFacts, finding: Dict[str, Any]) -> Plan:
    """Missing / Wide Hierarchy -> give the role an explicit shared interface."""
    smell = finding.get("smell_type", "Missing Hierarchy")
    comps = finding.get("components") or []
    fqn = comps[0] if comps else ""
    if not facts.file_for(fqn):
        return Plan(smell, "Introduce Supertype", comps, applicable=False, stock=False,
                    reason=f"{fqn} not found in the source index", evidence={"component": fqn})

    group = _sibling_group(facts, fqn)
    if len(group) < 2:
        return Plan(smell, "Introduce Supertype", comps, applicable=False, stock=False,
                    reason=f"only {len(group)} concrete class(es) share {fqn.rsplit('.', 1)[-1]}'s "
                           "role, so there is no group to abstract over; a supertype for one "
                           "class adds indirection without removing the smell",
                    evidence={"component": fqn, "group": group})

    pkg = fqn.rsplit(".", 1)[0]
    stem = _name_stem(fqn.rsplit(".", 1)[-1])
    iface = f"{pkg}.{stem}Contract"
    if facts.file_for(iface):
        return Plan(smell, "Introduce Supertype", comps, applicable=False, stock=False,
                    reason=f"{iface} already exists", evidence={"component": fqn})

    # The interface file itself is created by the loop (see `supertypes` on the Plan) because
    # OpenRewrite's CreateEmptyJavaClass cannot express "in the same source root as X".
    plan = Plan(smell, "Introduce Supertype", comps, stock=False, resolves_fully=True,
                entries=[RecipeEntry("com.dsarp.recipes.IntroduceSupertype",
                                     {"fullyQualifiedInterfaceName": iface,
                                      "classNames": ",".join(group)})],
                reason=f"give {len(group)} '{stem}' classes the shared "
                       f"{iface.rsplit('.', 1)[-1]} contract they are missing",
                evidence={"component": fqn, "new_interface": iface, "classes": group[:8]})
    plan.evidence["creates_interface"] = iface
    return plan


def plan_broken_modularization(facts: SourceFacts, finding: Dict[str, Any]) -> Plan:
    """Broken Modularization = data and the methods using it live apart.

    The textbook fix is Move Method / Move Field, which requires member-level analysis of
    every call site. rewrite-java has no move-method recipe and writing a safe one needs type
    attribution DSARP's regex index does not have, so this is reported rather than guessed at.
    """
    comps = finding.get("components") or []
    fqn = comps[0] if comps else ""
    txt = facts.text_of(fqn)
    fields = len(re.findall(r"^[ \t]{1,8}(?:public|private|protected)\s+[\w.<>\[\]]+\s+\w+\s*[;=]",
                            txt, re.M)) if txt else 0
    methods = len(re.findall(r"^[ \t]{1,8}(?:public|private|protected)\s+[\w.<>\[\]\s]+\s+\w+\s*\(",
                             txt, re.M)) if txt else 0
    return Plan("Broken Modularization", "Move Method / Move Field", comps, applicable=False,
                stock=False,
                reason=f"{fqn.rsplit('.', 1)[-1]} separates its data from the behaviour that "
                       f"uses it ({fields} fields, {methods} methods). Fixing it means moving "
                       "individual members between types and rewriting every call site; no "
                       "stock recipe does that, and DSARP's index lacks the type attribution "
                       "to do it safely",
                evidence={"component": fqn, "fields": fields, "methods": methods})


def create_interface_files(repo_path: Path, interfaces: Dict[str, List[str]]) -> Dict[str, Any]:
    """Write the empty interfaces that IntroduceSupertype will make classes implement.

    Done here rather than with OpenRewrite's CreateEmptyJavaClass because the new type must
    land in the same source root as the classes that will implement it, which that recipe
    cannot express. An empty interface is always legal to implement, so the result compiles.
    """
    created = []
    for iface, siblings in interfaces.items():
        pkg, simple = iface.rsplit(".", 1)
        anchor = None
        for s in siblings:
            rel = s.replace(".", "/") + ".java"
            for cand in Path(repo_path).rglob(Path(rel).name):
                if str(cand).replace("\\", "/").endswith(rel):
                    anchor = cand
                    break
            if anchor:
                break
        if anchor is None:
            continue
        target = anchor.parent / f"{simple}.java"
        if target.exists():
            continue
        target.write_text(
            f"package {pkg};\n\n"
            f"/** Shared contract extracted by DSARP to give these types an explicit\n"
            f"  * common abstraction (Missing/Wide Hierarchy). */\n"
            f"public interface {simple} {{\n}}\n", encoding="utf-8")
        created.append(iface)
    return {"interfaces_created": created, "count": len(created)}
