"""Guards for the post-refactoring tidy shared by the Spoon and OpenRewrite arms.

Each case here is a failure that cost a measured run, not a hypothetical.
"""
from dsarp.refactoring.java_text import (drop_same_package_imports, idents, import_fqn,
                                         package_of, relocate_to_match_package,
                                         source_root_of_file, strip_unused_imports,
                                         tidy_tree)


def test_only_plain_single_type_imports_are_candidates():
    assert import_fqn("import java.util.List;") == "java.util.List"
    assert import_fqn("import static java.util.Arrays.asList;") is None
    assert import_fqn("import java.util.regex.*;") is None
    assert import_fqn("class C {}") is None


def test_drops_the_import_spoon_invented_from_a_lambda():
    """The pdfbox failure: Consumer imported into a file that never names it."""
    src = ("package a.b;\n"
           "import java.util.List;\n"
           "import java.util.function.Consumer;\n"
           "public class C { List<String> x; void f() { x.forEach(s -> g(s)); } }\n")
    out, dropped = strip_unused_imports(src)
    assert dropped == ["java.util.function.Consumer"]
    assert "import java.util.List;" in out


def test_a_substring_of_a_longer_name_is_not_a_use():
    src = "package a;\nimport java.util.List;\nclass C { MyListener q; }\n"
    assert strip_unused_imports(src)[1] == ["java.util.List"]


def test_javadoc_mention_keeps_the_import():
    src = "package a;\nimport java.util.Map;\n/** see {@link Map} */\nclass C {}\n"
    assert strip_unused_imports(src)[1] == []


def test_same_package_import_is_dropped():
    """The OpenRewrite failure on TreeStatus -> ui, which Spoon survived."""
    src = "package org.x.ui;\nimport org.x.ui.TreeStatus;\nclass C { TreeStatus s; }\n"
    out, dropped = drop_same_package_imports(src)
    assert dropped == ["org.x.ui.TreeStatus"]
    assert "TreeStatus s;" in out


def test_a_genuine_cross_package_import_survives():
    src = "package org.x.ui;\nimport org.y.Other;\nclass C { Other o; }\n"
    assert drop_same_package_imports(src)[1] == []


def test_package_and_root_detection():
    assert package_of("// c\npackage a.b.c;\nimport x.Y;\n") == "a.b.c"
    assert source_root_of_file("/r/src/main/java/a/b/C.java") == "/r/src/main/java/"
    assert source_root_of_file("/r/no/markers/C.java") is None


def test_relocates_a_file_whose_package_no_longer_matches_its_directory(tmp_path):
    """ChangeType can rewrite the package and leave the file where it was."""
    d = tmp_path / "src" / "main" / "java" / "old" / "pkg"
    d.mkdir(parents=True)
    (d / "C.java").write_text("package new.pkg;\nclass C {}\n", encoding="utf-8")
    moved = relocate_to_match_package(tmp_path)
    assert len(moved) == 1
    assert (tmp_path / "src/main/java/new/pkg/C.java").exists()
    assert not (d / "C.java").exists()


def test_tidy_tree_is_a_noop_on_a_clean_tree(tmp_path):
    d = tmp_path / "src" / "main" / "java" / "a"
    d.mkdir(parents=True)
    f = d / "C.java"
    f.write_text("package a;\nimport java.util.List;\nclass C { List<String> x; }\n",
                 encoding="utf-8")
    before = f.read_text(encoding="utf-8")
    r = tidy_tree(tmp_path)
    assert r["files_relocated"] == [] and not r["unused_imports_dropped"]
    assert f.read_text(encoding="utf-8") == before


def test_idents_splits_on_non_identifier_characters():
    assert idents("new ArrayList<>(); foo.bar") == {"new", "ArrayList", "foo", "bar"}


def _repo(tmp_path, files):
    root = tmp_path / "src" / "main" / "java"
    for rel, body in files.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")
    return tmp_path


def test_moved_file_regains_imports_for_types_it_left_behind(tmp_path):
    """The pdfbox TreeStatusPane failure: moved to ui, still naming TreeStatus in treestatus.

    ChangeType rewrites references TO the moved type and leaves references FROM it alone,
    so the moved file stopped compiling with `cannot find symbol`.
    """
    from dsarp.refactoring.java_text import add_origin_imports
    repo = _repo(tmp_path, {
        "a/ts/Pane.java": "package a.ui;\npublic class Pane { private Status s; }\n",
        "a/ts/Status.java": "package a.ts;\npublic class Status {}\n",
    })
    # the mover already relocated the file's package but not its directory
    from dsarp.refactoring.java_text import relocate_to_match_package
    relocate_to_match_package(repo)
    added = add_origin_imports(repo, [("a.ts.Pane", "a.ui.Pane")])
    assert list(added.values()) == [["Status"]]
    moved = repo / "src/main/java/a/ui/Pane.java"
    assert "import a.ts.Status;" in moved.read_text(encoding="utf-8")


def test_no_import_added_when_the_name_is_unused(tmp_path):
    from dsarp.refactoring.java_text import add_origin_imports, relocate_to_match_package
    repo = _repo(tmp_path, {
        "a/ts/Pane.java": "package a.ui;\npublic class Pane { int x; }\n",
        "a/ts/Status.java": "package a.ts;\npublic class Status {}\n",
    })
    relocate_to_match_package(repo)
    assert add_origin_imports(repo, [("a.ts.Pane", "a.ui.Pane")]) == {
        (repo / "src/main/java/a/ui/Pane.java").as_posix(): []}


def test_no_import_added_for_a_move_within_one_package(tmp_path):
    from dsarp.refactoring.java_text import add_origin_imports
    repo = _repo(tmp_path, {"a/Pane.java": "package a;\nclass Pane { Status s; }\n"})
    assert add_origin_imports(repo, [("a.Pane", "a.Pane")]) == {}


def test_cwd_relative_changed_file_paths_are_resolved(tmp_path, monkeypatch):
    """OpenRewrite reports changed files relative to the maven process cwd, not the repo.

    Joining them onto repo_path produced paths that did not exist, so every file was skipped
    and the tidy silently did nothing while pdfbox kept failing on RedundantImport.
    """
    from dsarp.refactoring.java_text import _java_files
    repo = tmp_path / "copy"
    f = repo / "src" / "main" / "java" / "a" / "C.java"
    f.parent.mkdir(parents=True)
    f.write_text("package a;\nclass C {}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    rel = "copy/src/main/java/a/C.java"           # relative to cwd, NOT to repo
    assert [q.resolve() for q in _java_files(repo, [rel])] == [f.resolve()]


def test_files_outside_the_repo_are_refused(tmp_path, monkeypatch):
    """A changed-file list must never let the tidy edit something outside the copy."""
    from dsarp.refactoring.java_text import _java_files
    repo = tmp_path / "copy"
    (repo / "src").mkdir(parents=True)
    outside = tmp_path / "Elsewhere.java"
    outside.write_text("package z;\nclass Elsewhere {}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert _java_files(repo, ["Elsewhere.java"]) == []


def test_add_implements_to_a_plain_class():
    from dsarp.refactoring.java_text import add_implements
    src = "package a;\n\npublic class Engine {\n    void go() {}\n}\n"
    out, ok = add_implements(src, "Engine", "b.EngineApi")
    assert ok and "class Engine implements EngineApi" in out
    assert "import b.EngineApi;" in out


def test_add_implements_appends_to_an_existing_list():
    from dsarp.refactoring.java_text import add_implements
    src = "package a;\nimport b.EngineApi;\npublic class Engine extends Base implements Foo {\n}\n"
    out, ok = add_implements(src, "Engine", "b.EngineApi")
    assert ok and "implements Foo, EngineApi" in out, out
    assert out.count("import b.EngineApi;") == 1, "import must not be duplicated"


def test_add_implements_is_idempotent():
    from dsarp.refactoring.java_text import add_implements
    src = "package a;\npublic class Engine implements EngineApi {\n}\n"
    out, ok = add_implements(src, "Engine", "b.EngineApi")
    assert ok and out.count("EngineApi") == 1, out


def test_add_implements_preserves_surrounding_formatting():
    """The whole reason this is textual: pdfbox failed on a reflowed 278-character line."""
    from dsarp.refactoring.java_text import add_implements
    long_line = "    // " + "x" * 150 + "\n"
    src = "package a;\n\npublic class Engine {\n" + long_line + "}\n"
    out, _ = add_implements(src, "Engine", "b.EngineApi")
    assert long_line in out, "untouched lines must survive byte-for-byte"


def test_retarget_type_swaps_declared_types_and_imports():
    from dsarp.refactoring.java_text import retarget_type
    src = ("package a;\nimport b.Engine;\n"
           "public class Runner {\n    private Engine e;\n"
           "    public Engine get() { return e; }\n}\n")
    out = retarget_type(src, "b.Engine", "a.EngineApi")
    assert "import b.Engine;" not in out
    assert "private EngineApi e;" in out and "public EngineApi get()" in out
    # Same package as the interface, so no import is needed.
    assert "import a.EngineApi;" not in out


def test_retarget_type_does_not_touch_longer_identifiers():
    from dsarp.refactoring.java_text import retarget_type
    src = "package a;\nimport b.Engine;\nclass R { Engine e; EngineFactory f; MyEngine m; }\n"
    out = retarget_type(src, "b.Engine", "a.EngineApi")
    assert "EngineFactory f;" in out and "MyEngine m;" in out, out
    assert "EngineApi e;" in out, out
