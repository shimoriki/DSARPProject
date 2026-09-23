"""A move renames a type; anything that names it as text keeps pointing at the old name."""
from dsarp.refactoring.name_refs import name_references
from dsarp.tools.arcan_runner import modules_for


def _repo(tmp_path):
    (tmp_path / "mod-a" / "src/main/java/com/app").mkdir(parents=True)
    (tmp_path / "mod-a" / "pom.xml").write_text("<project/>", encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    return tmp_path


def test_a_service_file_naming_the_class_is_reported(tmp_path):
    r = _repo(tmp_path)
    svc = r / "mod-a/src/main/resources/META-INF/services/com.app.Detector"
    svc.parent.mkdir(parents=True)
    svc.write_text("com.app.Thing\n", encoding="utf-8")
    res = name_references(r, "com.app.Thing")
    assert res["needs_manual_fixup"] and res["resources"]


def test_an_ordinary_java_reference_is_not_flagged(tmp_path):
    r = _repo(tmp_path)
    (r / "mod-a/src/main/java/com/app/User.java").write_text(
        "package com.app;\nimport com.app.Thing;\nclass User { Thing t; }\n", encoding="utf-8")
    # the compiler rewrites these; flagging them would flag every candidate
    assert not name_references(r, "com.app.Thing")["needs_manual_fixup"]


def test_a_class_named_in_a_string_literal_is_flagged(tmp_path):
    r = _repo(tmp_path)
    (r / "mod-a/src/main/java/com/app/Loader.java").write_text(
        'package com.app;\nclass Loader { Class<?> c = Class.forName("com.app.Thing"); }\n',
        encoding="utf-8")
    assert name_references(r, "com.app.Thing")["string_literals"]


def test_changed_files_map_to_the_modules_that_own_them(tmp_path):
    r = _repo(tmp_path)
    f = r / "mod-a/src/main/java/com/app/User.java"
    f.write_text("class User {}", encoding="utf-8")
    assert modules_for(r, [f]) == ["mod-a"]


def test_a_file_owned_by_the_root_pom_cannot_be_scoped(tmp_path):
    r = _repo(tmp_path)
    (r / "src/main/java").mkdir(parents=True)
    f = r / "src/main/java/Root.java"
    f.write_text("class Root {}", encoding="utf-8")
    assert modules_for(r, [f]) == ["."]
