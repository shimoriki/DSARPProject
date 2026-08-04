"""Tests for the refactoring safety guards.

These guards are what stop DSARP from emitting a refactoring that does not compile, or from
reporting a measurement failure as a success. Each test below corresponds to a real broken
build or a real false result observed during development, so a regression here would
re-introduce a bug that actually happened.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from dsarp.refactoring.agents import plan_all
from dsarp.refactoring.params import SEARCH_SPACE, RefactoringParams
from dsarp.refactoring.strategies import SourceFacts
from dsarp.verification.iterative_loop import per_type_delta, targeted_score
from dsarp.verification.openrewrite_loop import _merge_is_safe


def _write(root: Path, fqn: str, body: str) -> Path:
    pkg, simple = fqn.rsplit(".", 1)
    d = root / "src" / "main" / "java" / Path(*pkg.split("."))
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{simple}.java"
    f.write_text(textwrap.dedent(body).strip() + "\n", encoding="utf-8")
    return f


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A tiny repo exercising every precondition the planner has to respect."""
    # a.Helper is PACKAGE-PRIVATE: anything using it cannot leave package a
    _write(tmp_path, "com.ex.a.Helper", """
        package com.ex.a;
        class Helper { static int twice(int n) { return n * 2; } }
    """)
    # uses the package-private Helper -> must be blocked from moving
    _write(tmp_path, "com.ex.a.UsesHelper", """
        package com.ex.a;
        public class UsesHelper { public int go(int n) { return Helper.twice(n); } }
    """)
    # references a PUBLIC sibling with no import -> movable, but needs an explicit import
    _write(tmp_path, "com.ex.a.Sibling", """
        package com.ex.a;
        public class Sibling { public int one() { return 1; } }
    """)
    _write(tmp_path, "com.ex.a.UsesSibling", """
        package com.ex.a;
        public class UsesSibling { public int go() { return new Sibling().one(); } }
    """)
    # package b has a class with the SAME simple name as one in a -> merge must be refused
    _write(tmp_path, "com.ex.b.Sibling", """
        package com.ex.b;
        public class Sibling { public int two() { return 2; } }
    """)
    # every package gets a package-info: it is NOT a type and must not count as a collision
    _write(tmp_path, "com.ex.a.package-info", "package com.ex.a;")
    _write(tmp_path, "com.ex.b.package-info", "package com.ex.b;")
    # dead, non-public, unreferenced -> the only safe deletion candidate
    _write(tmp_path, "com.ex.b.Dead", """
        package com.ex.b;
        class Dead { int unused() { return 0; } }
    """)
    return tmp_path


# --------------------------------------------------------------------------- #
# package-private access: a move that would not compile
# --------------------------------------------------------------------------- #

def test_class_using_package_private_type_cannot_move(repo):
    facts = SourceFacts(repo)
    blockers = facts.move_blockers("com.ex.a.UsesHelper")
    assert blockers, "using a package-private sibling must block the move"
    assert any("Helper" in b for b in blockers)


def test_class_using_only_public_siblings_can_move(repo):
    facts = SourceFacts(repo)
    assert facts.move_blockers("com.ex.a.UsesSibling") == []


def test_public_type_is_not_reported_package_private(repo):
    """Regression: truncating the file at the first '{' hid the declaration behind the
    licence header and marked every public type as package-private."""
    facts = SourceFacts(repo)
    types, _members = facts._package_private("com.ex.a")
    assert "Sibling" not in types
    assert "Helper" in types


# --------------------------------------------------------------------------- #
# same-package references that a move would strand
# --------------------------------------------------------------------------- #

def test_stranded_sibling_is_detected(repo):
    facts = SourceFacts(repo)
    sibs = facts.siblings_referenced_by("com.ex.a.UsesSibling")
    assert "com.ex.a.Sibling" in sibs, "moving this class would strand its sibling reference"


# --------------------------------------------------------------------------- #
# package merges
# --------------------------------------------------------------------------- #

def test_merge_refused_on_simple_name_collision(repo):
    assert _merge_is_safe(repo, "com.ex.a", "com.ex.b") is False


def test_package_info_does_not_count_as_a_collision(repo):
    """Regression: package-info.java exists in every package; counting it as a class made
    any two packages look like they shared a type and blocked all merges."""
    facts = SourceFacts(repo)
    names = {c.rsplit(".", 1)[-1] for c in facts.classes_in("com.ex.a")}
    assert "package-info" not in names


# --------------------------------------------------------------------------- #
# dead code deletion needs hard evidence
# --------------------------------------------------------------------------- #

def test_unreferenced_non_public_class_is_deletable(repo):
    facts = SourceFacts(repo)
    assert facts.reference_count("com.ex.b.Dead") == 0


def test_referenced_class_is_not_deletable(repo):
    facts = SourceFacts(repo)
    assert facts.reference_count("com.ex.a.Sibling") > 0


# --------------------------------------------------------------------------- #
# agent routing: nothing may be silently dropped
# --------------------------------------------------------------------------- #

def test_every_finding_is_routed_to_an_agent(repo):
    findings = [
        {"smell_type": "God Component", "components": ["com.ex.a"]},
        {"smell_type": "Deficient Encapsulation", "components": ["com.ex.a.Sibling"]},
        {"smell_type": "Broken Hierarchy", "components": ["com.ex.a.Sibling"]},
        {"smell_type": "Dense Structure", "components": ["com.ex.a"]},
        {"smell_type": "Missing Hierarchy", "components": ["com.ex.a.Sibling"]},
    ]
    routed = plan_all(repo, findings)
    assert routed["unrouted_smell_types"] == []
    assert len(routed["plans"]) == len(findings)
    # a plan that cannot be automated must still explain itself
    for p in routed["plans"]:
        assert p.applicable or p.reason, f"{p.smell_type} was dropped without a reason"


def test_cyclic_is_left_to_the_loop(repo):
    """Cyclic dependency is planned by the package-merge planner, not an agent."""
    routed = plan_all(repo, [{"smell_type": "Cyclic Dependency", "components": ["com.ex.a"]}])
    assert routed["plans"] == []


# --------------------------------------------------------------------------- #
# reporting: judge a run on what it targeted
# --------------------------------------------------------------------------- #

def test_targeted_score_ignores_untargeted_smells():
    by_type = {"Unstable Dependency": 3, "Feature Concentration": 9}
    assert targeted_score(by_type, ["Unstable Dependency"]) == 3


def test_side_effects_are_reported_separately():
    before = {"God Component": 3, "Feature Concentration": 0}
    after = {"God Component": 2, "Feature Concentration": 3}
    d = per_type_delta(before, after, ["God Component"])
    assert d["targeted_removed"] == 1
    assert any(r["smell_type"] == "Feature Concentration" for r in d["side_effects"])


# --------------------------------------------------------------------------- #
# tunable parameters
# --------------------------------------------------------------------------- #

def test_params_round_trip(tmp_path):
    p = RefactoringParams(god_component_min_classes=99)
    path = p.save(tmp_path / "params.json")
    assert RefactoringParams.load(path).god_component_min_classes == 99


def test_correctness_parameters_are_not_tunable():
    """Raising these buys a better score by deleting or hiding code that is still used."""
    assert "dead_code_max_references" not in SEARCH_SPACE
    assert "encapsulate_max_external_readers" not in SEARCH_SPACE
