"""DSARP's custom recipes bind their options only if the module keeps parameter names.

OpenRewrite matches a declarative recipe's options to CONSTRUCTOR PARAMETER NAMES. javac discards
those unless told to keep them, so without `<parameters>true</parameters>` the reflected names are
`arg0, arg1, arg2`, every option binds to nothing, and the plugin reports each one as "is required"
while `rewrite:discover` still lists them all correctly -- which makes it look like a YAML problem.

Measured: before the flag, `ReduceFieldVisibility` and `ReplaceMagicNumberWithConstant` both failed
with three "is required" errors and changed no files. After it, both bind and the magic-number
recipe changed its file. The three recipes the AI catalogue advertises had never received an option.

The flag is one line in a pom that nothing else would fail on, so this guards it.
"""
from pathlib import Path

import pytest

POM = Path(__file__).resolve().parents[1] / "tools" / "dsarp-recipes" / "pom.xml"


@pytest.mark.skipif(not POM.exists(), reason="tools/ is not checked in; nothing to guard here")
def test_the_recipe_module_keeps_constructor_parameter_names():
    text = POM.read_text(encoding="utf-8")
    assert "<parameters>true</parameters>" in text, (
        "dsarp-recipes must compile with -parameters, or every custom recipe silently receives "
        "null for all of its options")


@pytest.mark.skipif(not POM.exists(), reason="tools/ is not checked in")
def test_every_recipe_declaring_options_has_a_json_creator():
    """An @Option without a @JsonCreator constructor cannot be built from YAML at all.

    Parameter names are necessary, not sufficient: the constructor still has to be the one Jackson
    picks, and these recipes mark it explicitly rather than relying on there being only one.
    """
    src = POM.parent / "src" / "main" / "java" / "com" / "dsarp" / "recipes"
    checked = 0
    for f in sorted(src.glob("*.java")):
        text = f.read_text(encoding="utf-8", errors="ignore")
        if "@Option" not in text:
            continue
        checked += 1
        assert "@JsonCreator" in text, "%s declares @Option but has no @JsonCreator" % f.name
        assert "@JsonProperty" in text, "%s declares @Option but names no @JsonProperty" % f.name
    assert checked >= 4, "expected the four option-taking recipes, found %d" % checked
