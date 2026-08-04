"""Tests for the gates that decide whether an LLM's proposal is allowed to run.

The model never gets the last word: a proposal must name a real recipe, use only options that
recipe accepts, and refer to types that exist. Each rejection below is a failure mode actually
observed from a local model, so these tests pin behaviour that was learned the hard way.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from dsarp.refactoring.ai_recipes import ALLOWED_RECIPES, _canonical, propose
from dsarp.refactoring.strategies import SourceFacts


class FakeModel:
    """Returns a canned response, so the gates are tested without a live model."""

    def __init__(self, payload):
        self.payload = payload

    def generate(self, prompt, max_tokens=600, temperature=0.1):
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return type("R", (), {"text": text})()


@pytest.fixture
def facts(tmp_path: Path) -> SourceFacts:
    d = tmp_path / "src" / "main" / "java" / "com" / "ex"
    d.mkdir(parents=True)
    (d / "Real.java").write_text(
        textwrap.dedent("""
            package com.ex;
            public class Real { public int v; }
        """).strip(), encoding="utf-8")
    (d / "Used.java").write_text(
        textwrap.dedent("""
            package com.ex;
            public class Used { }
        """).strip(), encoding="utf-8")
    (d / "Caller.java").write_text(
        textwrap.dedent("""
            package com.ex;
            public class Caller { Used u = new Used(); }
        """).strip(), encoding="utf-8")
    return SourceFacts(tmp_path)


FINDING = {"smell_type": "Deficient Encapsulation", "components": ["com.ex.Real"]}


def test_hallucinated_recipe_is_rejected_without_running(facts):
    p = propose(FakeModel({"reasoning": "x", "recipes": [
        {"recipe": "org.openrewrite.java.MagicallyFixEverything", "options": {}}]}), facts, FINDING)
    assert not p.valid
    assert "hallucinated" in p.rejection or "disallowed" in p.rejection


def test_bare_recipe_name_is_accepted(facts):
    """A model omitting the package prefix is a formatting slip, not a hallucination."""
    assert _canonical("ReduceFieldVisibility") == "com.dsarp.recipes.ReduceFieldVisibility"
    p = propose(FakeModel({"reasoning": "x", "recipes": [
        {"recipe": "ReduceFieldVisibility",
         "options": {"fullyQualifiedClassName": "com.ex.Real", "fieldName": "v"}}]}),
        facts, FINDING)
    assert p.valid, p.rejection


def test_unknown_option_is_rejected(facts):
    p = propose(FakeModel({"reasoning": "x", "recipes": [
        {"recipe": "com.dsarp.recipes.ReduceFieldVisibility",
         "options": {"fullyQualifiedClassName": "com.ex.Real", "fieldName": "v",
                     "makeItFaster": True}}]}), facts, FINDING)
    assert not p.valid
    assert "does not accept" in p.rejection


def test_nonexistent_type_is_rejected(facts):
    p = propose(FakeModel({"reasoning": "x", "recipes": [
        {"recipe": "com.dsarp.recipes.ReduceFieldVisibility",
         "options": {"fullyQualifiedClassName": "com.ex.DoesNotExist", "fieldName": "v"}}]}),
        facts, FINDING)
    assert not p.valid
    assert "does not exist" in p.rejection


def test_deleting_a_referenced_class_is_rejected(facts):
    """Observed for real: the model's own reasoning said the class was still referenced,
    and it proposed deleting it anyway."""
    p = propose(FakeModel({"reasoning": "it is still referenced", "recipes": [
        {"recipe": "org.openrewrite.DeleteSourceFiles",
         "options": {"filePattern": ".*Used\\.java"}}]}),
        facts, {"smell_type": "Unutilized Abstraction", "components": ["com.ex.Used"]})
    assert not p.valid
    assert "still reference" in p.rejection and "com.ex.Used" in p.rejection


def test_declining_is_recorded_separately_from_failure(facts):
    """Refusing to act can be the correct answer and must not be scored as a failure."""
    p = propose(FakeModel({"reasoning": "no recipe can fix this", "recipes": []}),
                facts, FINDING)
    assert not p.valid
    assert p.declined


def test_non_json_response_is_rejected(facts):
    p = propose(FakeModel("I think you should refactor it manually."), facts, FINDING)
    assert not p.valid
    assert not p.declined
    assert "JSON" in p.rejection


def test_model_failure_does_not_raise(facts):
    class Broken:
        def generate(self, *a, **k):
            raise RuntimeError("connection refused")

    p = propose(Broken(), facts, FINDING)
    assert not p.valid
    assert "model call failed" in p.rejection


def test_catalogue_only_lists_recipes_that_exist():
    """Every allowed recipe is either stock OpenRewrite or one DSARP actually ships."""
    src = Path(__file__).resolve().parent.parent / "tools" / "dsarp-recipes" / "src"
    for name in ALLOWED_RECIPES:
        if not name.startswith("com.dsarp."):
            continue
        simple = name.rsplit(".", 1)[-1]
        assert list(src.rglob(f"{simple}.java")), f"{name} has no implementation"


# --------------------------------------------------------------------------- #
# Guards added after the Qwen-7B trial: the model produced structurally valid
# proposals that were semantically wrong in ways the strategies already guard against.
# --------------------------------------------------------------------------- #

def test_list_valued_option_is_normalised(facts, tmp_path):
    """Observed: classNames: ['a.B'] matched nothing and reported a false "no effect"."""
    d = tmp_path / "src" / "main" / "java" / "com" / "ex"
    (d / "Iface.java").write_text("package com.ex;\npublic interface Iface { }\n",
                                  encoding="utf-8")
    f2 = SourceFacts(tmp_path)
    p = propose(FakeModel({"reasoning": "x", "recipes": [
        {"recipe": "com.dsarp.recipes.IntroduceSupertype",
         "options": {"fullyQualifiedInterfaceName": "com.ex.Iface",
                     "classNames": ["com.ex.Real", "com.ex.Used"]}}]}),
        f2, {"smell_type": "Wide Hierarchy", "components": ["com.ex.Real"]})
    assert p.valid, p.rejection
    assert p.entries[0].options["classNames"] == "com.ex.Real,com.ex.Used"


def test_test_code_target_is_rejected(tmp_path):
    """Observed: asked about Wide Hierarchy, the model targeted AbstractCommonTest."""
    d = tmp_path / "src" / "test" / "java" / "com" / "ex"
    d.mkdir(parents=True)
    (d / "SomeTest.java").write_text("package com.ex;\npublic class SomeTest { public int v; }\n",
                                     encoding="utf-8")
    f2 = SourceFacts(tmp_path)
    p = propose(FakeModel({"reasoning": "x", "recipes": [
        {"recipe": "com.dsarp.recipes.ReduceFieldVisibility",
         "options": {"fullyQualifiedClassName": "com.ex.SomeTest", "fieldName": "v"}}]}),
        f2, {"smell_type": "Deficient Encapsulation", "components": ["com.ex.SomeTest"]})
    assert not p.valid
    assert "test code" in p.rejection


def test_supertype_must_already_exist(facts):
    """IntroduceSupertype adds `implements X`; if X is not declared it cannot compile."""
    p = propose(FakeModel({"reasoning": "x", "recipes": [
        {"recipe": "com.dsarp.recipes.IntroduceSupertype",
         "options": {"fullyQualifiedInterfaceName": "com.ex.NeverDeclared",
                     "classNames": "com.ex.Real"}}]}),
        facts, {"smell_type": "Wide Hierarchy", "components": ["com.ex.Real"]})
    assert not p.valid
    assert "does not exist" in p.rejection
