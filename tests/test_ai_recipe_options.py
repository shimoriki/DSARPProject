"""Two option mistakes that cost entire OpenRewrite runs on log4j2.

Both were the model doing something plausible that nothing checked, so the failure only
surfaced hours later as a broken build or an empty result.
"""
import tempfile
from pathlib import Path

from dsarp.refactoring.ai_recipes import propose
from dsarp.refactoring.strategies import SourceFacts


class _Reply:
    """A model that always returns the given JSON."""
    def __init__(self, text):
        self.text, self.model, self.name = text, "fake", "fake"

    def generate(self, *_, **__):
        return self


def _facts():
    root = Path(tempfile.mkdtemp(prefix="airec-"))
    for rel, body in {
        "src/main/java/a/b/One.java": "package a.b;\npublic class One { }\n",
        "src/main/java/a/b/Two.java": "package a.b;\npublic class Two { }\n",
        "src/main/java/a/c/Other.java": "package a.c;\npublic class Other { }\n",
    }.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return SourceFacts(root)


FINDING = {"smell_type": "Cyclic Dependency", "components": ["a.b"], "description": "d"}


def test_comma_list_in_a_single_class_option_is_named_precisely():
    """nemotron-mini put four classes into fullyQualifiedClassName on 17 findings running,
    every one rejected as "does not exist", leaving the model with zero valid recipes."""
    p = propose(_Reply('{"reasoning": "r", "recipes": [{"recipe": '
                       '"com.dsarp.recipes.ExtractInterfaceForClass", "options": '
                       '{"fullyQualifiedClassName": "a.b.One,a.b.Two", '
                       '"fullyQualifiedInterfaceName": "a.b.Iface"}}]}'), _facts(), FINDING)
    assert "takes ONE value, got 2" in p.rejection
    assert "classNames" in p.rejection, "the message should say which option does take a list"


def test_invented_target_package_is_refused():
    """phi4-mini proposed twenty ChangePackage recipes into placeholder names and
    OpenRewrite composed them, producing
    `...status.moved5.moved4.moved3.moved2.moved.moved5...` and a dead build."""
    p = propose(_Reply('{"reasoning": "r", "recipes": [{"recipe": '
                       '"org.openrewrite.java.ChangePackage", "options": '
                       '{"oldPackageName": "a.b", "newPackageName": "a.b.moved"}}]}'),
                _facts(), FINDING)
    assert "does not exist" in p.rejection and "moved" in p.rejection


def test_a_real_target_package_still_passes():
    p = propose(_Reply('{"reasoning": "r", "recipes": [{"recipe": '
                       '"org.openrewrite.java.ChangePackage", "options": '
                       '{"oldPackageName": "a.b", "newPackageName": "a.c"}}]}'),
                _facts(), FINDING)
    assert not p.rejection, p.rejection
    assert len(p.entries) == 1
