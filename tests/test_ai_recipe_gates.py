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
