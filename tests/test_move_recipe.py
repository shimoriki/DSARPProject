"""A move is more than a type change, and the recipe has to say so.

ChangeType alone left pdfbox's debugger-app/pom.xml naming the old <mainClass> and tika's
TikaCLITest asserting the old FQN as a string literal -- both invisible to a type-aware
recipe, both fatal at run time.
"""
import yaml

from dsarp.openrewrite.runner import write_migration_recipe, write_move_recipe

MOVE = [("com.app.Thing", "com.app.core.Thing")]


def _recipes(path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    out = []
    for entry in doc["recipeList"]:
        if isinstance(entry, str):
            out.append((entry, {}))
        else:
            ((name, opts),) = entry.items()
            out.append((name, opts))
    return out


def test_a_move_recipe_covers_types_strings_text_and_imports(tmp_path):
    names = [n for n, _ in _recipes(write_move_recipe(tmp_path, MOVE))]
    assert names[0] == "org.openrewrite.java.ChangeType"
    assert "org.openrewrite.java.ChangeTypeInStringLiteral" in names
    assert "org.openrewrite.text.FindAndReplace" in names
    # imports last: the passes above are what leave them unused
    assert names[-1] == "org.openrewrite.java.RemoveUnusedImports"


def test_the_text_pass_targets_the_files_that_name_classes(tmp_path):
    globs = [o["filePattern"] for n, o in _recipes(write_move_recipe(tmp_path, MOVE))
             if n == "org.openrewrite.text.FindAndReplace"]
    assert "**/pom.xml" in globs and "**/META-INF/services/*" in globs
    opts = [o for n, o in _recipes(write_move_recipe(tmp_path, MOVE))
            if n == "org.openrewrite.text.FindAndReplace"][0]
    assert opts["find"] == "com.app.Thing" and opts["replace"] == "com.app.core.Thing"
    assert opts["caseSensitive"] is True


def test_a_migration_recipe_never_rewrites_someone_elses_text_files(tmp_path):
    p = write_migration_recipe(tmp_path / "META-INF/rewrite/migration.yml", MOVE)
    names = [n for n, _ in _recipes(p)]
    assert "org.openrewrite.java.ChangeType" in names
    assert "org.openrewrite.text.FindAndReplace" not in names
    assert not (tmp_path / "META-INF/rewrite/rewrite.yml").exists()
