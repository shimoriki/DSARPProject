"""Let an LLM propose OpenRewrite recipes for smells we have no strategy for — then TEST them.

The model never gets the last word. It proposes a declarative recipe composed from a fixed
catalogue of known-real recipes; DSARP then runs it through the same closed loop everything
else goes through, and keeps it only if the refactored code

  1. still COMPILES, and
  2. measurably reduces the targeted smell according to the real tools.

That inverts the usual risk of LLM-generated refactoring. A hallucinated recipe name fails
validation before it ever runs; a plausible-but-useless recipe fails the measurement gate; a
harmful one fails the build gate. Only a proposal that survives real tool measurement is
recorded as viable, and every verdict cites the numbers it was judged on.

Proposals and verdicts are appended to data/outputs/<repo>/ai_recipe_trials.json so the
catalogue of what the model gets right (and wrong) accumulates as evidence.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .strategies import RecipeEntry

# Recipes the model is allowed to compose. Anything outside this set is rejected without
# being run — an LLM inventing a plausible recipe name is the most likely failure mode.
ALLOWED_RECIPES: Dict[str, List[str]] = {
    "org.openrewrite.java.ChangeType": ["oldFullyQualifiedTypeName", "newFullyQualifiedTypeName"],
    "org.openrewrite.java.ChangePackage": ["oldPackageName", "newPackageName", "recursive"],
    "org.openrewrite.java.ChangeMethodAccessLevel": ["methodPattern", "newAccessLevel"],
    "org.openrewrite.java.ChangeMethodName": ["methodPattern", "newMethodName"],
    "org.openrewrite.java.ChangeFieldName": ["classType", "hasName", "newName"],
    "org.openrewrite.java.RemoveUnusedImports": [],
    "org.openrewrite.DeleteSourceFiles": ["filePattern"],
    "com.dsarp.recipes.ReduceFieldVisibility": ["fullyQualifiedClassName", "fieldName"],
    "com.dsarp.recipes.ExtractInterfaceForClass": ["fullyQualifiedClassName",
                                                   "fullyQualifiedInterfaceName"],
    "com.dsarp.recipes.IntroduceSupertype": ["fullyQualifiedInterfaceName", "classNames"],
}

# Telling the model only the recipe NAMES made it conclude the catalogue "cannot create new
# types" and decline — when two of these do exactly that. Each entry says what it achieves.
RECIPE_EFFECTS: Dict[str, str] = {
    "org.openrewrite.java.ChangeType": "relocate/rename ONE class and rewrite every reference",
    "org.openrewrite.java.ChangePackage": "relocate an ENTIRE package and rewrite references",
    "org.openrewrite.java.ChangeMethodAccessLevel": "widen or narrow a method's visibility",
    "org.openrewrite.java.ChangeMethodName": "rename a method and every call site",
    "org.openrewrite.java.ChangeFieldName": "rename a field and every access",
    "org.openrewrite.java.RemoveUnusedImports": "delete unused imports",
    "org.openrewrite.DeleteSourceFiles": "delete a source file (only if nothing references it)",
    "com.dsarp.recipes.ReduceFieldVisibility": "make an exposed field private",
    "com.dsarp.recipes.ExtractInterfaceForClass":
        "CREATE a NEW interface from a class's public methods and make the class implement it "
        "(use this to invert a dependency)",
    "com.dsarp.recipes.IntroduceSupertype":
        "CREATE a NEW shared interface and make several named classes implement it "
        "(use this to give related classes a common abstraction)",
}


def _canonical(name: str) -> str:
    """Accept a bare recipe name; models routinely drop the package prefix.

    `ExtractInterfaceForClass` names a real recipe — treating that as a hallucination
    penalises the model for a formatting slip rather than a factual error.
    """
    name = (name or "").strip()
    if name in ALLOWED_RECIPES:
        return name
    # Match on the SIMPLE name of whatever was written, so both a bare name
    # ("RemoveUnusedImports") and a wrong package ("org.openrewrite.RemoveUnusedImports"
    # instead of org.openrewrite.java.*) resolve. Recipe simple names are unique here, and
    # getting the package wrong is a recall slip, not an invented recipe.
    simple = name.rsplit(".", 1)[-1]
    matches = [full for full in ALLOWED_RECIPES if full.rsplit(".", 1)[-1] == simple]
    return matches[0] if len(matches) == 1 else name

PROMPT = """You are an expert Java architect using OpenRewrite.

A static analysis tool reported this architectural smell:

  smell:      {smell}
  component:  {component}
  evidence:   {evidence}

Facts about the code (from the repository index — treat as ground truth):
{facts}

Propose an OpenRewrite recipe that would REDUCE this smell without breaking compilation.

You may ONLY use these recipes, with exactly these options:
{catalogue}

RULES — a proposal breaking any of these is discarded without being run:
 1. Use full recipe names and only the options listed above.
 2. Every class, package and interface you name must appear in the facts above.
 3. Never target a TEST class.
 4. Never move a class listed as MUST NOT be moved.
 5. Never delete a class that has external references.
 6. IntroduceSupertype only works with an interface that ALREADY exists.
 7. Options are strings. For several classes write "a.B,a.C" — never a JSON list.

Reply with JSON only, no prose:
{{"reasoning": "<one sentence>", "recipes": [{{"recipe": "<name>", "options": {{...}}}}]}}

If no available recipe can address this smell under these rules, reply:
{{"reasoning": "<why>", "recipes": []}}
Proposing a recipe that cannot help is worse than proposing none."""


@dataclass
class Proposal:
    smell_type: str
    component: str
    reasoning: str = ""
    entries: List[RecipeEntry] = field(default_factory=list)
    valid: bool = False
    declined: bool = False
    rejection: str = ""
    raw: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"smell_type": self.smell_type, "component": self.component,
                "reasoning": self.reasoning, "valid": self.valid,
                "declined": self.declined, "rejection": self.rejection,
                "recipes": [{"recipe": e.recipe, "options": e.options} for e in self.entries]}


def _facts_for(facts, component: str) -> str:
    """Factual context INCLUDING the preconditions, so the model can satisfy them up front.

    Earlier versions stated only what the component was, then rejected proposals afterwards
    for violating rules the model was never told. Every rejection reason the validator can
    produce is now derivable from this block: which classes may be moved, which are test
    code, and which interfaces actually exist.
    """
    lines = []
    jf = facts.file_for(component)
    if jf:
        pkg = component.rsplit(".", 1)[0]
        lines.append(f"- {component} is a class in package {pkg}")
        lines.append(f"- external references to it: {facts.reference_count(component)}")
        exposed = facts.exposed_fields(component)
        lines.append(f"- public/protected fields: "
                     + (", ".join(exposed[:6]) if exposed else "(none — nothing to encapsulate)"))
        blockers = facts.move_blockers(component)
        if blockers:
            lines.append(f"- MUST NOT be moved out of its package: {blockers[0]}")
        else:
            lines.append("- may be moved to another package")
    else:
        pkg = component
        classes = facts.classes_in(component)
        if not classes:
            return f"- {component} was not found in the source index"
        lines.append(f"- {component} is a package with {len(classes)} production classes")

    # Which siblings are safe to touch, and which are off-limits. Stating this removes the
    # two mistakes the model made unprompted: targeting test code, and moving a class that
    # depends on package-private members.
    movable, blocked, tests = [], [], []
    for fqn in facts.classes_in(pkg, production_only=False)[:40]:
        f = facts.file_for(fqn)
        simple = fqn.rsplit(".", 1)[-1]
        if f is not None and facts.is_test(f):
            tests.append(simple)
        elif facts.move_blockers(fqn):
            blocked.append(simple)
        else:
            movable.append(simple)
    if movable:
        lines.append(f"- classes in {pkg} that MAY be moved: {', '.join(movable[:10])}")
    if blocked:
        lines.append(f"- classes that MUST NOT be moved (package-private deps): "
                     f"{', '.join(blocked[:6])}")
    if tests:
        lines.append(f"- TEST classes — never refactor these: {', '.join(tests[:6])}")

    # IntroduceSupertype can only implement an interface that already exists.
    ifaces = [c.rsplit(".", 1)[-1] for c in facts.classes_in(pkg)
              if re.search(rf"\binterface\s+{re.escape(c.rsplit('.', 1)[-1])}\b",
                           facts.text_of(c))]
    lines.append(f"- interfaces that ALREADY exist in {pkg}: "
                 + (", ".join(ifaces[:8]) if ifaces else
                    "(none — so IntroduceSupertype is NOT usable here)"))
    return "\n".join(lines)


def _catalogue() -> str:
    lines = []
    for name, opts in ALLOWED_RECIPES.items():
        lines.append(f"  {name}")
        lines.append(f"      effect:  {RECIPE_EFFECTS.get(name, '')}")
        lines.append(f"      options: {', '.join(opts) if opts else '(none)'}")
    return "\n".join(lines)


def propose(model, facts, finding: Dict[str, Any]) -> Proposal:
    """Ask the model for a recipe, then validate it against the allowed catalogue."""
    smell = finding.get("smell_type", "?")
    comps = finding.get("components") or []
    component = comps[0] if comps else ""
    prompt = PROMPT.format(smell=smell, component=component,
                           evidence=finding.get("description", "")[:300] or "(none)",
                           facts=_facts_for(facts, component), catalogue=_catalogue())
    p = Proposal(smell_type=smell, component=component)
    try:
        try:
            p.raw = (model.generate(prompt, max_tokens=600, temperature=0.1,
                                    json_mode=True).text or "")
        except TypeError:              # provider without json_mode support
            p.raw = (model.generate(prompt, max_tokens=600, temperature=0.1).text or "")
    except Exception as e:                                  # model unavailable / timed out
        p.rejection = f"model call failed: {e}"
        return p

    m = re.search(r"\{.*\}", p.raw, re.S)
    if not m:
        p.rejection = "model did not return JSON"
        return p
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        p.rejection = f"model returned invalid JSON: {e}"
        return p

    p.reasoning = str(data.get("reasoning", ""))[:300]
    proposed = data.get("recipes") or []
    if not proposed:
        # Declining can be the CORRECT answer — e.g. refusing to delete a type that is still
        # referenced. Recorded separately so a good refusal is not scored as a failure.
        p.declined = True
        p.rejection = "model declined: " + (p.reasoning[:160] or "no reason given")
        return p

    for item in proposed:
        name = _canonical((item or {}).get("recipe", ""))
        opts = (item or {}).get("options") or {}
        if name not in ALLOWED_RECIPES:
            p.rejection = f"hallucinated or disallowed recipe: {name!r}"
            return p
        allowed = set(ALLOWED_RECIPES[name])
        unknown = set(opts) - allowed
        if unknown:
            p.rejection = f"{name} does not accept option(s): {sorted(unknown)}"
            return p
        missing = allowed - set(opts)
        if missing and name != "org.openrewrite.java.ChangePackage":
            p.rejection = f"{name} is missing required option(s): {sorted(missing)}"
            return p
        # Models emit JSON lists where a recipe wants a comma-separated string
        # (classNames: ['a.B'] silently matches nothing and the run reports "no effect").
        for key, value in list(opts.items()):
            if isinstance(value, list):
                opts[key] = ",".join(str(v) for v in value)

        # The hand-written strategies refuse to refactor test code, and an AI proposal must
        # meet the same bar — a model asked about "Wide Hierarchy" proposed giving a
        # supertype to AbstractCommonTest.
        for key in ("fullyQualifiedClassName", "classType", "classNames",
                    "oldFullyQualifiedTypeName"):
            for target in str(opts.get(key, "")).split(","):
                target = target.strip()
                jf = facts.file_for(target) if target else None
                if jf is not None and facts.is_test(jf):
                    p.rejection = f"{key}={target!r} is test code; DSARP refactors production only"
                    return p

        # IntroduceSupertype / ExtractInterface need the new type to exist before the recipe
        # adds `implements` for it. The strategy path writes it first; a bare AI proposal
        # does not, so the result would not compile.
        if name in ("com.dsarp.recipes.IntroduceSupertype",
                    "com.dsarp.recipes.ExtractInterfaceForClass"):
            iface = str(opts.get("fullyQualifiedInterfaceName", ""))
            if name.endswith("IntroduceSupertype") and not facts.file_for(iface):
                p.rejection = (f"{iface} does not exist; IntroduceSupertype can only implement "
                               "an interface that is already declared")
                return p

        # entity check: every type/package named must actually exist
        for key, value in opts.items():
            if key.startswith("old") or key == "fullyQualifiedClassName" or key == "classType":
                if not (facts.file_for(str(value)) or facts.classes_in(str(value))):
                    p.rejection = f"{key}={value!r} does not exist in this repository"
                    return p
        # Safety pre-check: models will propose deleting a file whose own stated reasoning
        # says it is still used. Caught here rather than by the build gate, because a wrong
        # deletion is cheap to refuse and expensive to discover.
        if name == "org.openrewrite.DeleteSourceFiles":
            # filePattern may be a glob OR a regex (".*Constants\\.java"), so pull the trailing
            # Java identifier out rather than treating it as a path.
            pattern = str(opts.get("filePattern", ""))
            m2 = re.search(r"([A-Za-z_]\w*)\s*\\?\.java\s*$", pattern)
            target = m2.group(1) if m2 else ""
            for fqn in [k for k in facts._file_of if k.rsplit(".", 1)[-1] == target]:
                refs = facts.reference_count(fqn)
                if refs > 0:
                    p.rejection = (f"proposes deleting {fqn}, which {refs} production file(s) "
                                   "still reference — the model's own reasoning said as much")
                    return p
        p.entries.append(RecipeEntry(name, opts))

    p.valid = True
    return p


def test_proposal(cfg, project_id: str, repo_path: Path, proposal: Proposal,
                  detector: str = "both") -> Dict[str, Any]:
    """Run a validated proposal through the real loop and judge it on measured results."""
    from ..verification.openrewrite_loop import _apply_and_verify, detect
    from ..verification.iterative_loop import score

    out = cfg.data_dir / "outputs" / project_id
    before = detect(Path(repo_path), out / f"ai_{detector}_before", detector)
    steps: List[Dict[str, Any]] = [{"step": "detect", "tool": before.get("tool"),
                                    "status": before.get("status"),
                                    "smells": before.get("smells")}]
    rep = _apply_and_verify(cfg, f"{project_id}__ai", Path(repo_path), out, steps, before,
                            detector, before.get("tool", detector), proposal.entries,
                            kind="composite", plans=[proposal.as_dict()],
                            keep_copy=True)

    # Only Arcan compiles (it reads bytecode). With a Designite-only detector there is NO
    # build signal at all, and reporting that as "did not compile" would be the very error
    # this project guards against: an unmeasured result presented as a measured failure.
    # So compile explicitly when the detector did not.
    build_status = rep.get("build_after_refactoring")
    if build_status is None:
        from ..tools.arcan_runner import compile_repo
        copy = Path(rep.get("refactored_copy") or "")
        build_status = (compile_repo(copy).get("status") if copy.exists()
                        else "not_verified")
    built = build_status == "compiled"
    b_by, a_by = rep.get("by_type_before") or {}, rep.get("by_type_after") or {}
    target_before = sum(n for s, n in b_by.items()
                        if proposal.smell_type.lower() in s.lower())
    target_after = sum(n for s, n in a_by.items()
                       if proposal.smell_type.lower() in s.lower())

    if build_status == "not_verified":
        verdict, why = "unverified", ("the build was never checked, so nothing can be "
                                      "concluded about this proposal")
    elif not built:
        verdict, why = "rejected", f"the refactored code did not compile ({build_status})"
    elif rep.get("verification_status") != "verified":
        verdict, why = "unverified", "no tool could measure the result"
    elif target_after < target_before:
        verdict, why = "viable", (f"{proposal.smell_type} {target_before} -> {target_after}")
    elif score(a_by) < score(b_by):
        verdict, why = "partially_viable", (
            f"{proposal.smell_type} unchanged, but overall architectural smells "
            f"{score(b_by)} -> {score(a_by)}")
    else:
        verdict, why = "no_effect", (
            f"compiles, but {proposal.smell_type} stayed at {target_after}")

    return {"proposal": proposal.as_dict(), "verdict": verdict, "why": why,
            "built": built, "build_status": build_status, "target_before": target_before, "target_after": target_after,
            "score_before": score(b_by), "score_after": score(a_by) if built else None,
            "files_changed": len(rep.get("changed_files") or [])}
