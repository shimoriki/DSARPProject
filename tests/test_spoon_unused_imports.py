"""Spoon's printer invents imports; this is the guard that they get pruned correctly.

pdfbox's build treats UnusedImports as an error. Spoon resolved the inferred functional
interface of `compoundWords.forEach(word -> ...)` and printed
`import java.util.function.Consumer;` into a file that never names Consumer. The build died
on that single line and Arcan then measured a tree that had not compiled, reporting
952 -> 2 smells. The verdict classifier caught it, but the run was lost.
"""
from dsarp.tools.spoon_runner import _idents, _strip_unused_imports

SRC = (
    "package a.b;\n"
    "import java.util.ArrayList;\n"
    "import java.util.List;\n"
    "import java.util.function.Consumer;\n"
    "import static java.util.Arrays.asList;\n"
    "import java.util.regex.*;\n"
    "public class C { List<String> x = new ArrayList<>(); }\n"
)


def test_drops_only_the_unused_import():
    out, dropped = _strip_unused_imports(SRC)
    assert dropped == ["java.util.function.Consumer"]
    assert "import java.util.List;" in out
    assert "import java.util.ArrayList;" in out


def test_leaves_static_and_wildcard_imports_alone():
    out, _ = _strip_unused_imports(SRC)
    assert "import static java.util.Arrays.asList;" in out
    assert "import java.util.regex.*;" in out


def test_a_javadoc_only_mention_keeps_its_import():
    src = "package a;\nimport java.util.Map;\n/** see {@link Map} */\nclass C {}\n"
    assert _strip_unused_imports(src)[1] == []


def test_a_substring_of_a_longer_name_does_not_count_as_use():
    """`List` must not be kept alive by `MyListener`, or nothing is ever pruned."""
    src = "package a;\nimport java.util.List;\nclass C { MyListener q; }\n"
    assert _strip_unused_imports(src)[1] == ["java.util.List"]


def test_idents_splits_on_non_identifier_characters():
    assert _idents("new ArrayList<>(); foo.bar") == {"new", "ArrayList", "foo", "bar"}
