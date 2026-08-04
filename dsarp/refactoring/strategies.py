"""Refactoring strategies for EVERY detected smell type — not just cyclic dependency.

Each strategy turns one tool finding into concrete OpenRewrite recipe entries, or explains
(with evidence) why no safe automated refactoring exists for it. The loop runs every
strategy, composes ONE recipe, executes it, and re-detects with the real tools.

Design notes that matter:

* **Moving a class out of its package breaks its sibling references.** A class that used to
  sit next to `Helper` referenced it with no import; once relocated it needs `import
  old.pkg.Helper`. OpenRewrite's ChangeType does not add those, and its `AddImport` recipe
  cannot either — with `onlyIfReferenced` it inspects the file while it is STILL in the old
  package, sees the sibling as already accessible, and adds nothing. So every move-based
  strategy records the needed imports in `Plan.pre_imports`, and `apply_pre_imports()`
  writes them into the copied sources BEFORE the recipe runs. Importing from your own
  package is legal Java, so the code compiles both before and after the move.

* **Evidence or nothing.** A strategy only fires when the source index confirms the entities
  exist. Otherwise it returns `not_applicable` with a reason, never a guess.
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .params import RefactoringParams

# Policy thresholds live in params.py so they can be tuned against the measured
# reward (build still compiles + smells actually reduced) instead of guessed.
PARAMS = RefactoringParams.load()

# ---------------------------------------------------------------------------- #
# recipe entry model
# ---------------------------------------------------------------------------- #


@dataclass
class RecipeEntry:
    """One OpenRewrite recipe invocation (rendered into rewrite.yml)."""
    recipe: str
    options: Dict[str, Any] = field(default_factory=dict)

    def to_yaml_lines(self, indent: str = "  ") -> List[str]:
        lines = [f"{indent}- {self.recipe}:"]
        for k, v in self.options.items():
            if isinstance(v, bool):
                v = "true" if v else "false"
            lines.append(f"{indent}    {k}: {v}")
        return lines


@dataclass
class Plan:
    """What a strategy decided to do about one finding."""
    smell_type: str
    refactoring: str
    components: List[str]
    entries: List[RecipeEntry] = field(default_factory=list)
    applicable: bool = True
    reason: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    stock: bool = True          # composed only from stock OpenRewrite recipes
    # FQN of a file -> sibling types that must be imported EXPLICITLY before it is moved
    pre_imports: Dict[str, List[str]] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"smell_type": self.smell_type, "refactoring": self.refactoring,
                "components": self.components[:6], "applicable": self.applicable,
                "reason": self.reason, "recipes": [e.recipe for e in self.entries],
                "operations": len(self.entries), "stock_recipes": self.stock,
                "evidence": self.evidence,
                "verification_status": "planned" if self.applicable
                else "requires_source_inspection"}


# ---------------------------------------------------------------------------- #
# source facts (evidence) — cached per repo
# ---------------------------------------------------------------------------- #


class SourceFacts:
    """Minimal, cached view of the repo: packages, classes, references."""

    def __init__(self, repo_path: Path):
        self.repo = Path(repo_path)
        self._files: Optional[List[Path]] = None
        self._pkg_of: Dict[Path, str] = {}
        self._classes: Dict[str, List[str]] = {}      # package -> [simple names]
        self._file_of: Dict[str, Path] = {}           # FQN -> file
        self._text: Dict[Path, str] = {}
        self._pkg_private_cache: Dict[str, Tuple[set, set]] = {}
        self._scan()

    def _scan(self) -> None:
        files = []
        for jf in self.repo.rglob("*.java"):
            p = str(jf).replace("\\", "/")
            if "/target/" in p or "/build/" in p:
                continue
            files.append(jf)
        self._files = files
        for jf in files:
            try:
                txt = jf.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            self._text[jf] = txt
            m = re.search(r"^\s*package\s+([\w.]+)\s*;", txt, re.M)
            if not m:
                continue
            pkg = m.group(1)
            self._pkg_of[jf] = pkg
            simple = jf.stem
            self._classes.setdefault(pkg, []).append(simple)
            self._file_of[f"{pkg}.{simple}"] = jf

    # -- queries -------------------------------------------------------------
    def is_test(self, jf: Path) -> bool:
        p = str(jf).replace("\\", "/")
        return "/test/" in p or p.endswith("Test.java")

    def packages(self) -> List[str]:
        return sorted(self._classes)

    def classes_in(self, pkg: str, production_only: bool = True) -> List[str]:
        out = []
        for fqn, jf in self._file_of.items():
            if fqn.rsplit(".", 1)[0] == pkg and (not production_only or not self.is_test(jf)):
                out.append(fqn)
        return sorted(out)

    def file_for(self, fqn: str) -> Optional[Path]:
        return self._file_of.get(fqn)

    def text_of(self, fqn: str) -> str:
        jf = self._file_of.get(fqn)
        return self._text.get(jf, "") if jf else ""

    def siblings_referenced_by(self, fqn: str) -> List[str]:
        """Same-package types the class uses WITHOUT an import (would dangle after a move)."""
        pkg = fqn.rsplit(".", 1)[0]
        txt = self.text_of(fqn)
        if not txt:
            return []
        body = re.sub(r"^\s*(package|import)\s+[\w.*]+\s*;", "", txt, flags=re.M)
        out = []
        for simple in self._classes.get(pkg, []):
            if simple == fqn.rsplit(".", 1)[-1]:
                continue
            if re.search(rf"\b{re.escape(simple)}\b", body):
                out.append(f"{pkg}.{simple}")
        return sorted(set(out))

    # -- move preconditions ---------------------------------------------------
    # Relocating a class out of its package severs access to every PACKAGE-PRIVATE type and
    # member it relied on — and unlike a missing import, nothing can restore that without
    # widening visibility, which changes the public API. So a move is only safe if the class
    # touches none of them.

    _TYPE_DECL = re.compile(
        r"^[ \t]*(?!.*\b(?:public|private|protected)\b)"
        r"(?:static\s+|final\s+|abstract\s+|sealed\s+)*"
        r"(?:class|interface|enum|record)\s+(\w+)", re.M)
    # A DECLARATION, not a call: `    static String toLocale(Locale l) {`.
    # The leading keyword guard stops statements like `return new Foo(` or `throw new Bar(`
    # from being mistaken for package-private members (which would block far too many moves).
    _STMT_KEYWORDS = (r"return|new|throw|else|case|catch|do|try|if|for|while|switch|"
                      r"assert|yield|break|continue|super|this")
    _MEMBER_DECL = re.compile(
        r"^[ \t]{1,8}(?!.*\b(?:public|private|protected)\b)"
        r"(?:static\s+|final\s+|synchronized\s+|native\s+|abstract\s+|default\s+)*"
        rf"(?!(?:{_STMT_KEYWORDS})\b)[\w.<>\[\]]+\s+"
        rf"(?!(?:{_STMT_KEYWORDS})\b)(\w+)\s*\([^;]*\)\s*(?:throws [\w.,\s]+)?\{{", re.M)

    def _package_private(self, pkg: str) -> Tuple[set, set]:
        """(package-private type names, package-private member names) declared in `pkg`."""
        if pkg in self._pkg_private_cache:
            return self._pkg_private_cache[pkg]
        types, members = set(), set()
        for fqn in self.classes_in(pkg, production_only=False):
            txt = self.text_of(fqn)
            if not txt:
                continue
            simple = fqn.rsplit(".", 1)[-1]
            # Scan the WHOLE file: truncating at the first "{" lands inside the licence
            # header on most Apache sources, hiding the real declaration and marking every
            # public type as package-private.
            if not re.search(
                    rf"\bpublic\s+(?:abstract\s+|final\s+|static\s+|sealed\s+|strictfp\s+)*"
                    rf"(?:class|interface|enum|record)\s+{re.escape(simple)}\b", txt):
                types.add(simple)
            members.update(self._MEMBER_DECL.findall(txt))
        self._pkg_private_cache[pkg] = (types, members)
        return types, members

    def move_blockers(self, fqn: str) -> List[str]:
        """Package-private things this class uses that a move would put out of reach."""
        pkg = fqn.rsplit(".", 1)[0]
        txt = self.text_of(fqn)
        if not txt:
            return []
        simple_self = fqn.rsplit(".", 1)[-1]
        types, members = self._package_private(pkg)
        blockers = []
        for t in types:
            if t == simple_self:
                continue
            if re.search(rf"\b{re.escape(t)}\b", txt):
                blockers.append(f"type {pkg}.{t} is package-private")
        for m in members:
            if re.search(rf"\b{re.escape(m)}\s*\(", txt) and f" {m}(" not in txt.split("{")[0]:
                blockers.append(f"member {m}() is package-private in {pkg}")
        return sorted(set(blockers))

    _FIELD_DECL = re.compile(
        r"^[ \t]{1,8}(public|protected)\s+"
        r"(?!(?:class|interface|enum|record|abstract)\b)"
        r"(?:static\s+|final\s+|transient\s+|volatile\s+)*"
        r"[\w.<>\[\],\s]+?\s+(\w+)\s*(?:=[^;]*)?;", re.M)

    def exposed_fields(self, fqn: str) -> List[str]:
        """public/protected NON-final fields — what Deficient Encapsulation flags."""
        txt = self.text_of(fqn)
        if not txt:
            return []
        out = []
        for m in self._FIELD_DECL.finditer(txt):
            line = txt[m.start():m.end()]
            if re.search(r"\bfinal\b", line) and re.search(r"\bstatic\b", line):
                continue           # public static final = a constant, not leaked state
            out.append(m.group(2))
        return sorted(set(out))

    def external_field_users(self, fqn: str, field: str) -> int:
        """Files outside the declaring class that could be reading the field.

        Conservative on purpose: a file counts when it names the declaring type AND uses
        `.field` (or `Type.field` directly). Bare `.field` alone is far too common to be
        evidence of anything, and over-counting only costs us a skipped refactoring, while
        under-counting would produce code that does not compile.
        """
        simple = fqn.rsplit(".", 1)[-1]
        own = self._file_of.get(fqn)
        dotted = re.compile(rf"\.\s*{re.escape(field)}\b")
        qualified = re.compile(rf"\b{re.escape(simple)}\s*\.\s*{re.escape(field)}\b")
        names_type = re.compile(rf"\b{re.escape(simple)}\b")
        n = 0
        for jf, txt in self._text.items():
            if jf == own:
                continue
            if qualified.search(txt) or (names_type.search(txt) and dotted.search(txt)):
                n += 1
        return n

    def reference_count(self, fqn: str) -> int:
        """How many OTHER production files mention this type."""
        simple = fqn.rsplit(".", 1)[-1]
        own = self._file_of.get(fqn)
        n = 0
        for jf, txt in self._text.items():
            if jf == own or self.is_test(jf):
                continue
            if re.search(rf"\b{re.escape(simple)}\b", txt):
                n += 1
        return n

    def crossing_classes(self, from_pkg: str, to_pkg: str) -> List[str]:
        """Classes in from_pkg that reference to_pkg (they create the from->to edge)."""
        out = []
        for fqn in self.classes_in(from_pkg):
            txt = self.text_of(fqn)
            if not txt:
                continue
            if re.search(rf"\b{re.escape(to_pkg)}\.", txt) or \
                    any(re.search(rf"\b{re.escape(s)}\b", txt)
                        for s in self._classes.get(to_pkg, [])):
                out.append(fqn)
        return out


# ---------------------------------------------------------------------------- #
# helpers shared by move-based strategies
# ---------------------------------------------------------------------------- #


def _move_entries(facts: SourceFacts, moves: Sequence[Tuple[str, str]]
                  ) -> Tuple[List[RecipeEntry], Dict[str, List[str]], Dict[str, List[str]]]:
    """ChangeType per class, plus the explicit imports each move needs to stay compilable.

    A class sitting next to `Helper` refers to it with no import. Once relocated it needs
    `import old.pkg.Helper` — and OpenRewrite's `AddImport` cannot supply it: with
    `onlyIfReferenced` it evaluates the file while it is STILL in the old package, sees the
    sibling as already accessible, and adds nothing. So the imports are written into the
    source ourselves *before* the recipe runs. Importing a type from your own package is
    legal Java, so the code compiles both before and after the move.
    """
    entries: List[RecipeEntry] = []
    # Drop any class that depends on package-private types/members — relocating it would
    # not compile, and widening visibility to compensate would change the public API.
    safe, blocked = [], {}
    for old, new in moves:
        b = facts.move_blockers(old)
        (safe.append((old, new)) if not b else blocked.setdefault(old, b[:3]))
    moves = safe
    moved = {old for old, _ in moves}
    pre_imports: Dict[str, List[str]] = {}
    for old, new in moves:
        stranded = [sib for sib in facts.siblings_referenced_by(old) if sib not in moved]
        if stranded:
            pre_imports[old] = stranded
        entries.append(RecipeEntry("org.openrewrite.java.ChangeType", {
            "oldFullyQualifiedTypeName": old,
            "newFullyQualifiedTypeName": new,
            "ignoreDefinition": False}))
    return entries, pre_imports, blocked


def apply_pre_imports(repo_path: Path, pre_imports: Dict[str, List[str]]) -> Dict[str, Any]:
    """Insert the explicit sibling imports into the (copied) sources. Returns a summary."""
    facts_repo = Path(repo_path)
    changed, added = 0, 0
    for fqn, siblings in pre_imports.items():
        rel = fqn.replace(".", "/") + ".java"
        matches = list(facts_repo.rglob(rel.split("/")[-1]))
        target = next((m for m in matches
                       if str(m).replace("\\", "/").endswith(rel)), None)
        if target is None:
            continue
        try:
            text = target.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        need = [s for s in siblings if f"import {s};" not in text]
        if not need:
            continue
        m = re.search(r"^\s*package\s+[\w.]+\s*;\s*$", text, re.M)
        if not m:
            continue
        block = "".join(f"\nimport {s};" for s in sorted(need))
        text = text[:m.end()] + block + text[m.end():]
        try:
            target.write_text(text, encoding="utf-8")
        except OSError:
            continue
        changed += 1
        added += len(need)
    return {"files_touched": changed, "imports_added": added}


def _name_collision(facts: SourceFacts, moves: Sequence[Tuple[str, str]]) -> List[str]:
    """Destinations that would end up with two types of the same simple name."""
    bad = []
    for old, new in moves:
        dst_pkg, simple = new.rsplit(".", 1)
        existing = {f.rsplit(".", 1)[-1] for f in facts.classes_in(dst_pkg)}
        if simple in existing:
            bad.append(new)
    return bad


# ---------------------------------------------------------------------------- #
# strategies
# ---------------------------------------------------------------------------- #


def plan_god_component(facts: SourceFacts, finding: Dict[str, Any]) -> Plan:
    """God Component = one package doing too much -> split it into cohesive sub-packages.

    Classes are grouped by a shared name stem (e.g. every *CheckDigit together). The largest
    group moves into `<pkg>.<stem>` — a brand-new package, so no name can collide.
    """
    comps = finding.get("components") or []
    pkg = comps[0] if comps else ""
    classes = facts.classes_in(pkg)
    if len(classes) < PARAMS.god_component_min_classes:
        return Plan("God Component", "Split Package", comps, applicable=False,
                    reason=f"package {pkg} has only {len(classes)} production classes "
                           f"(threshold {PARAMS.god_component_min_classes}); "
                           "splitting would not reduce the smell",
                    evidence={"classes": len(classes)})
    groups: Dict[str, List[str]] = collections.defaultdict(list)
    for fqn in classes:
        simple = fqn.rsplit(".", 1)[-1]
        stem = _name_stem(simple)
        if stem:
            groups[stem].append(fqn)
    best = max((g for g in groups.items()
                if len(g[1]) >= PARAMS.god_component_min_group),
               key=lambda g: len(g[1]),
               default=None)
    if not best:
        return Plan("God Component", "Split Package", comps, applicable=False,
                    reason=f"no cohesive group of >={PARAMS.god_component_min_group} similarly-named "
                           f"classes found in {pkg}; "
                           "splitting it needs a human judgement call on responsibilities",
                    evidence={"classes": len(classes), "groups": len(groups)})
    stem, members = best
    sub = f"{pkg}.{stem.lower()}"
    moves = [(fqn, f"{sub}.{fqn.rsplit('.', 1)[-1]}") for fqn in members]
    entries, pre, blocked = _move_entries(facts, moves)
    if not entries:
        return Plan("God Component", "Split Package", comps, applicable=False,
                    reason=f"every '{stem}' class in {pkg} depends on package-private types or "
                           "members, so relocating it would not compile (widening visibility "
                           "would change the public API)",
                    evidence={"package": pkg, "blocked": dict(list(blocked.items())[:3])})
    return Plan("God Component", "Split Package", comps, entries=entries, pre_imports=pre,
                reason=f"move {len(entries)} of {len(members)} '{stem}' classes out of {pkg} "
                       f"into {sub}" + (f"; {len(blocked)} blocked by package-private access"
                                        if blocked else ""),
                evidence={"package": pkg, "classes_in_package": len(classes),
                          "extracted_group": stem, "moved": len(entries),
                          "blocked_by_package_private": dict(list(blocked.items())[:3]),
                          "new_package": sub})


def _name_stem(simple: str) -> str:
    """Trailing CamelCase word: AbstractCalendarValidator -> Validator."""
    parts = re.findall(r"[A-Z][a-z0-9]*", simple)
    return parts[-1] if len(parts) >= 2 else ""


def plan_scattered_functionality(facts: SourceFacts, finding: Dict[str, Any]) -> Plan:
    """Scattered Functionality = one concern spread over packages -> consolidate it."""
    comps = [c for c in (finding.get("components") or []) if c]
    pkg = comps[0] if comps else ""
    classes = facts.classes_in(pkg)
    if not classes:
        return Plan("Scattered Functionality", "Consolidate Package", comps, applicable=False,
                    reason=f"no production classes found for {pkg}",
                    evidence={"package": pkg})
    # find the same name-stem living in OTHER packages and pull it back together
    stems = collections.Counter(_name_stem(c.rsplit(".", 1)[-1]) for c in classes)
    stem = next((s for s, _ in stems.most_common() if s), "")
    if not stem:
        return Plan("Scattered Functionality", "Consolidate Package", comps, applicable=False,
                    reason="could not identify a dominant concern to consolidate",
                    evidence={"package": pkg})
    # Prefer the peer packages the tool itself named as realising the same concern.
    peers = [p for p in (finding.get("related") or []) if p and p != pkg]
    candidates = peers or [p for p in facts.packages()
                           if p != pkg and not p.startswith(pkg + ".")]
    scattered = []
    for other in candidates:
        if other == pkg:
            continue
        for fqn in facts.classes_in(other):
            if _name_stem(fqn.rsplit(".", 1)[-1]) == stem:
                scattered.append(fqn)
    if not scattered:
        return Plan("Scattered Functionality", "Consolidate Package", comps, applicable=False,
                    reason=f"the '{stem}' concern is not actually split across packages",
                    evidence={"package": pkg, "concern": stem})
    moves = [(f, f"{pkg}.{f.rsplit('.', 1)[-1]}") for f in scattered]
    collide = _name_collision(facts, moves)
    moves = [m for m in moves if m[1] not in collide]
    if not moves:
        return Plan("Scattered Functionality", "Consolidate Package", comps, applicable=False,
                    reason=f"every candidate move collides with an existing class in {pkg}",
                    evidence={"collisions": collide[:5]})
    entries, pre, blocked = _move_entries(facts, moves)
    return Plan("Scattered Functionality", "Consolidate Package", comps,
                entries=entries, pre_imports=pre,
                reason=f"pull {len(moves)} scattered '{stem}' classes into {pkg}",
                evidence={"package": pkg, "concern": stem, "moved": len(moves),
                          "skipped_collisions": collide[:5]})


def plan_unstable_dependency(facts: SourceFacts, finding: Dict[str, Any]) -> Plan:
    """Unstable Dependency = a package depends on ones less stable than itself.

    The mechanical part we CAN do safely: relocate the few classes that create the offending
    outgoing edge. Full Dependency Inversion (extract an interface both sides depend on)
    needs a new type, which no stock recipe can synthesise.
    """
    comps = [c for c in (finding.get("components") or []) if c]
    # Arcan names both packages in the finding; Designite names only the unstable one and
    # lists its less-stable dependencies in the Description (parsed into `related`).
    peers = [p for p in (finding.get("related") or []) if p and p not in comps]
    targets = comps[1:] + peers
    if not comps or not targets:
        return Plan("Unstable Dependency", "Dependency Inversion", comps, applicable=False,
                    reason="the tool did not name which less-stable component this package "
                           "depends on, so there is no grounded target to refactor toward",
                    evidence={"components": comps})
    src, dst = comps[0], targets[0]
    crossing = facts.crossing_classes(src, dst)
    if not crossing:
        return Plan("Unstable Dependency", "Dependency Inversion", comps, applicable=False,
                    reason=f"no source-level classes in {src} were found referencing {dst}; "
                           "the dependency may be via bytecode/reflection only",
                    evidence={"from": src, "to": dst})
    if len(crossing) > PARAMS.unstable_max_crossing:
        return Plan("Unstable Dependency", "Dependency Inversion", comps, applicable=False,
                    reason=f"{len(crossing)} classes in {src} depend on {dst}; relocating them "
                           "all would be a rewrite, not a refactoring — needs an extracted "
                           "interface (no stock OpenRewrite recipe synthesises new types)",
                    evidence={"from": src, "to": dst, "crossing": len(crossing)})
    moves = [(f, f"{dst}.{f.rsplit('.', 1)[-1]}") for f in crossing]
    collide = _name_collision(facts, moves)
    moves = [m for m in moves if m[1] not in collide]
    if not moves:
        return Plan("Unstable Dependency", "Move Class", comps, applicable=False,
                    reason=f"all crossing classes collide with existing names in {dst}",
                    evidence={"collisions": collide[:5]})
    entries, pre, blocked = _move_entries(facts, moves)
    return Plan("Unstable Dependency", "Move Class", comps, entries=entries, pre_imports=pre,
                reason=f"move {len(moves)} class(es) from {src} into {dst}, removing the "
                       "unstable outgoing dependency",
                evidence={"from": src, "to": dst, "moved": len(moves)})


def plan_unutilized_abstraction(facts: SourceFacts, finding: Dict[str, Any]) -> Plan:
    """Unutilized Abstraction = a type nobody uses -> delete it, but only on hard evidence."""
    comps = finding.get("components") or []
    fqn = comps[0] if comps else ""
    jf = facts.file_for(fqn)
    if not jf:
        return Plan("Unutilized Abstraction", "Remove Dead Code", comps, applicable=False,
                    reason=f"{fqn} not found in the source index",
                    evidence={"component": fqn})
    if facts.is_test(jf):
        # Test classes are invoked by the test runner, not by production references, so a
        # zero-reference count says nothing about whether they are dead.
        return Plan("Unutilized Abstraction", "Remove Dead Code", comps, applicable=False,
                    reason=f"{fqn} is test code — it is executed by the test runner, not "
                           "referenced from production, so it is never safe to delete on a "
                           "reference count",
                    evidence={"component": fqn, "test_code": True})
    refs = facts.reference_count(fqn)
    if refs > PARAMS.dead_code_max_references:
        return Plan("Unutilized Abstraction", "Remove Dead Code", comps, applicable=False,
                    reason=f"{fqn} is still referenced by {refs} production file(s); deleting "
                           "it would break the build",
                    evidence={"component": fqn, "references": refs})
    if re.search(r"\bpublic\s+(final\s+|abstract\s+)?(class|interface|enum|record)\b",
                 facts.text_of(fqn)):
        return Plan("Unutilized Abstraction", "Remove Dead Code", comps, applicable=False,
                    reason=f"{fqn} is public API — unused inside this repo, but removing it "
                           "would be a breaking change for downstream consumers",
                    evidence={"component": fqn, "references": 0, "public_api": True})
    rel = str(jf.relative_to(facts.repo)).replace("\\", "/")
    return Plan("Unutilized Abstraction", "Remove Dead Code", comps,
                entries=[RecipeEntry("org.openrewrite.DeleteSourceFiles",
                                     {"filePattern": rel})],
                reason=f"{fqn} has zero references and is not public API",
                evidence={"component": fqn, "references": 0, "file": rel})


def plan_deficient_encapsulation(facts: SourceFacts, finding: Dict[str, Any]) -> Plan:
    """Deficient Encapsulation = exposed field -> narrow it to private.

    Uses DSARP's custom `ReduceFieldVisibility` recipe: rewrite-java has
    ChangeMethodAccessLevel but no field equivalent. Narrowing only compiles when nothing
    outside the declaring class touches the field, so that is checked here first — the
    recipe stays simple and never rewrites call sites.
    """
    comps = finding.get("components") or []
    fqn = comps[0] if comps else ""
    txt = facts.text_of(fqn)
    if not txt:
        return Plan("Deficient Encapsulation", "Encapsulate Field", comps, applicable=False,
                    reason=f"{fqn} not found in the source index", stock=False,
                    evidence={"component": fqn})
    exposed = facts.exposed_fields(fqn)
    if not exposed:
        return Plan("Deficient Encapsulation", "Encapsulate Field", comps, applicable=False,
                    reason=f"no public/protected instance fields found in {fqn} to narrow",
                    stock=False, evidence={"component": fqn})
    simple = fqn.rsplit(".", 1)[-1]
    safe, blocked = [], []
    for field in exposed:
        users = facts.external_field_users(fqn, field)
        (safe.append(field) if not users else blocked.append(f"{field} (read by {users} file(s))"))
    if not safe:
        return Plan("Deficient Encapsulation", "Encapsulate Field", comps, applicable=False,
                    reason=f"every exposed field of {simple} is read from outside the class; "
                           "narrowing them needs accessor generation plus call-site rewriting",
                    stock=False,
                    evidence={"component": fqn, "blocked": blocked[:5]})
    entries = [RecipeEntry("com.dsarp.recipes.ReduceFieldVisibility",
                           {"fullyQualifiedClassName": fqn, "fieldName": f}) for f in safe]
    return Plan("Deficient Encapsulation", "Encapsulate Field", comps, entries=entries,
                stock=False,
                reason=f"make {len(safe)} unreferenced field(s) of {simple} private"
                       + (f"; {len(blocked)} left alone (read externally)" if blocked else ""),
                evidence={"component": fqn, "fields": safe[:8],
                          "blocked_external_reads": blocked[:5]})


def plan_extract_interface(facts: SourceFacts, finding: Dict[str, Any]) -> Plan:
    """Rebellious Hierarchy -> extract an interface to define the real contract.

    Uses DSARP's custom `ExtractInterfaceForClass`, which exposes rewrite-java's
    ExtractInterface machinery (shipped only as a visitor) as a nameable recipe. This is the
    one refactoring family that SYNTHESISES a new type, so it reaches smells that no amount
    of relocation can fix.
    """
    comps = finding.get("components") or []
    fqn = comps[0] if comps else ""
    jf = facts.file_for(fqn)
    if not jf:
        return Plan(finding.get("smell_type", "Rebellious Hierarchy"), "Extract Interface",
                    comps, applicable=False, stock=False,
                    reason=f"{fqn} not found in the source index", evidence={"component": fqn})
    txt = facts.text_of(fqn)
    simple = fqn.rsplit(".", 1)[-1]
    if not re.search(rf"\bclass\s+{re.escape(simple)}\b", txt):
        return Plan(finding.get("smell_type", "Rebellious Hierarchy"), "Extract Interface",
                    comps, applicable=False, stock=False,
                    reason=f"{simple} is not a class (interfaces/enums cannot have an "
                           "interface extracted from them)", evidence={"component": fqn})
    # rewrite-java's ExtractInterface copies the type's `extends` clause onto the new
    # interface, which is illegal when the supertype is a class ("interface expected here").
    if re.search(rf"\bclass\s+{re.escape(simple)}\b[^{{]*\bextends\b", txt):
        return Plan(finding.get("smell_type", "Rebellious Hierarchy"), "Extract Interface",
                    comps, applicable=False, stock=False,
                    reason=f"{simple} extends a superclass; the extracted interface would "
                           "inherit that `extends` clause, which Java forbids for interfaces",
                    evidence={"component": fqn, "has_superclass": True})
    iface = f"{fqn}Api"
    if facts.file_for(iface):
        return Plan(finding.get("smell_type", "Rebellious Hierarchy"), "Extract Interface",
                    comps, applicable=False, stock=False,
                    reason=f"{iface} already exists", evidence={"component": fqn})
    return Plan(finding.get("smell_type", "Rebellious Hierarchy"), "Extract Interface", comps,
                entries=[RecipeEntry("com.dsarp.recipes.ExtractInterfaceForClass",
                                     {"fullyQualifiedClassName": fqn,
                                      "fullyQualifiedInterfaceName": iface})],
                stock=False,
                reason=f"extract {iface.rsplit('.', 1)[-1]} from {simple} to define an explicit "
                       "contract for its dependents",
                evidence={"component": fqn, "new_interface": iface})


def plan_not_automatable(smell: str, refactoring: str, why: str):
    def _plan(facts: SourceFacts, finding: Dict[str, Any]) -> Plan:
        return Plan(smell, refactoring, finding.get("components") or [], applicable=False,
                    reason=why, stock=False)
    return _plan


# smell type (lower-cased, matched by substring) -> planner
STRATEGIES = {
    "god component": plan_god_component,
    "scattered functionality": plan_scattered_functionality,
    "unstable dependency": plan_unstable_dependency,
    "unutilized abstraction": plan_unutilized_abstraction,
    "unnecessary abstraction": plan_unutilized_abstraction,
    "feature concentration": plan_god_component,
    "hub-like dependency": plan_god_component,
    # Documented as not automatable — each needs a NEW type or a member-level rewrite that no
    # stock OpenRewrite recipe can synthesise. Reported with the reason, never silently skipped.
    "insufficient modularization": plan_not_automatable(
        "Insufficient Modularization", "Extract Class",
        "splitting a god class means inventing a new type and deciding which members move — "
        "no stock recipe synthesises types; needs human design input"),
    "deficient encapsulation": plan_deficient_encapsulation,
    "broken hierarchy": plan_not_automatable(
        "Broken Hierarchy", "Replace Inheritance with Delegation",
        "changing a supertype relationship alters public API and semantics; not safely automatable"),
    "wide hierarchy": plan_not_automatable(
        "Wide Hierarchy", "Introduce Intermediate Abstraction",
        "needs a new intermediate type chosen by a human"),
    "missing hierarchy": plan_not_automatable(
        "Missing Hierarchy", "Extract Superclass",
        "needs a new supertype and a judgement about which members are common"),
    "rebellious hierarchy": plan_extract_interface,
    "broken modularization": plan_not_automatable(
        "Broken Modularization", "Move Method/Field",
        "member-level relocation between types; needs per-member analysis"),
    "multifaceted abstraction": plan_not_automatable(
        "Multifaceted Abstraction", "Extract Class",
        "class has multiple responsibilities; splitting requires human design input"),
    "dense structure": plan_not_automatable(
        "Dense Structure", "Architectural Restructuring",
        "a repo-wide dependency-density problem; no single local refactoring addresses it"),
}


def plan_for(facts: SourceFacts, finding: Dict[str, Any]) -> Optional[Plan]:
    """Dispatch a finding to its strategy. Cyclic smells are handled by the loop itself."""
    smell = (finding.get("smell_type") or "").lower()
    if "cyclic" in smell:
        return None                     # package-merge path owns cyclic dependency
    # Refactoring is restricted to production code: rearranging test sources does not fix
    # architecture, and the detectors report smells for test classes too.
    comps = finding.get("components") or []
    if comps:
        jf = facts.file_for(comps[0])
        if jf is not None and facts.is_test(jf):
            return Plan(finding.get("smell_type", "?"), "n/a", comps, applicable=False,
                        reason="finding is in test code; DSARP only refactors production "
                               "sources", stock=False,
                        evidence={"component": comps[0], "test_code": True})
    for key, planner in STRATEGIES.items():
        if key in smell:
            return planner(facts, finding)
    return Plan(finding.get("smell_type", "?"), "unknown",
                finding.get("components") or [], applicable=False,
                reason="no refactoring strategy is registered for this smell type", stock=False)
