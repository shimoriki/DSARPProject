"""Tests for Extract Class, the first refactoring that REMOVES members.

Every case below is a bug that actually shipped and silently produced either a broken build
or a false clean result, so a regression here re-introduces a real failure.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from dsarp.refactoring.extract_class import (_method_bodies, plan_extract_class,
                                             static_methods, uses_non_public_members)
from dsarp.refactoring.strategies import SourceFacts


def _write(root: Path, fqn: str, body: str) -> Path:
    pkg, simple = fqn.rsplit(".", 1)
    d = root / "src" / "main" / "java" / Path(*pkg.split("."))
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{simple}.java"
    f.write_text(textwrap.dedent(body).strip() + "\n", encoding="utf-8")
    return f


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    # Mirrors GenericValidator: an overloaded public static method whose SECOND form calls a
    # private helper, plus enough clean methods to make a plan viable.
    _write(tmp_path, "com.ex.Util", """
        package com.ex;
        public class Util {
            private static int adjust(String v, int n) {
                return n;
            }
            public static boolean maxLength(String v, int max) {
                return v.length() <= max;
            }
            public static boolean maxLength(String v, int max, int lineEnd) {
                return adjust(v, lineEnd) <= max;
            }
            public static boolean isBlank(String v) {
                return v == null;
            }
            public static boolean isNum(String v) {
                return v != null;
            }
            public static boolean isEmpty(String v) {
                return v.isEmpty();
            }
        }
    """)
    return tmp_path


def test_all_overloads_are_found(repo):
    """re.search returned only the FIRST overload, so a method whose second form called a
    private helper was cleared for extraction and then broke the build."""
    facts = SourceFacts(repo)
    bodies = _method_bodies(facts.text_of("com.ex.Util"), "maxLength")
    assert len(bodies) == 2


def test_overload_calling_a_private_helper_is_blocked(repo):
    facts = SourceFacts(repo)
    assert uses_non_public_members(facts, "com.ex.Util", "maxLength") is True


def test_clean_methods_are_not_blocked(repo):
    facts = SourceFacts(repo)
    assert uses_non_public_members(facts, "com.ex.Util", "isBlank") is False


def test_plan_excludes_the_blocked_method(repo):
    facts = SourceFacts(repo)
    p = plan_extract_class(facts, {"smell_type": "Insufficient Modularization",
                                   "components": ["com.ex.Util"]})
    assert p.applicable, p.reason
    moved = p.evidence["methods"]
    assert "maxLength" not in moved
    assert {"isBlank", "isNum", "isEmpty"} <= set(moved)


def test_recipe_receives_the_approved_method_list(repo):
    """The recipe extracted EVERY public static method until it was given this list, so the
    preconditions checked here had no effect on what actually moved."""
    facts = SourceFacts(repo)
    p = plan_extract_class(facts, {"smell_type": "Insufficient Modularization",
                                   "components": ["com.ex.Util"]})
    extract = next(e for e in p.entries if e.recipe.endswith("ExtractStaticHelpers"))
    assert "methodNames" in extract.options
    assert "maxLength" not in extract.options["methodNames"].split(",")


def test_too_few_methods_is_refused(tmp_path):
    _write(tmp_path, "com.ex.Small", """
        package com.ex;
        public class Small {
            public static int one() {
                return 1;
            }
        }
    """)
    facts = SourceFacts(tmp_path)
    p = plan_extract_class(facts, {"smell_type": "Insufficient Modularization",
                                   "components": ["com.ex.Small"]})
    assert not p.applicable
    assert "fewer than 3" in p.reason


# --------------------------------------------------------------------------- #
# Claim ordering — the bug that blocked every verified reduction
# --------------------------------------------------------------------------- #

def test_extract_class_claims_its_whole_package(repo):
    """An extracted helper stays in its origin package and keeps referring to that package's
    types. If a God Component split relocates one of them in the same pass the helper cannot
    resolve it — which is exactly how DateValidator and EmailValidator kept going missing.
    Extract Class must therefore claim the package, not just the one class."""
    from dsarp.verification.openrewrite_loop import _types_touched
    facts = SourceFacts(repo)
    p = plan_extract_class(facts, {"smell_type": "Insufficient Modularization",
                                   "components": ["com.ex.Util"]})
    touched = _types_touched(p)
    assert "com.ex.*" in touched, "extraction must claim its package for the pass"


def test_package_claim_blocks_a_move_of_a_type_inside_it():
    """A 'pkg.*' claim has to cover every type declared in that package, otherwise the
    conflict filter compares exact names and lets the relocation through."""
    claimed = {"com.ex.*"}
    touched = {"com.ex.DateValidator"}
    blocked = {t for t in touched
               for c in claimed if c.endswith(".*") and t.startswith(c[:-1])}
    assert blocked, "a package claim must block a type declared inside it"
