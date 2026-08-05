"""A source package named `build` must survive being copied.

`shutil.ignore_patterns("build")` matches any directory of that name at any depth.
`org.apache.commons.io.build` is a real commons-io source package, so every working copy
lost it and failed to compile with 88 "package does not exist" errors - before a single
refactoring was applied. Every measurement taken on those copies was invalid.
"""
from dsarp.verification.effect_checker import _copy_repo


def _make_repo(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "pom.xml").write_text("<project/>", encoding="utf-8")
    src = root / "src/main/java/org/apache/commons/io/build"
    src.mkdir(parents=True)
    (src / "AbstractOrigin.java").write_text(
        "package org.apache.commons.io.build;\npublic class AbstractOrigin {}\n",
        encoding="utf-8")
    out = root / "target/classes"
    out.mkdir(parents=True)
    (out / "Stale.class").write_bytes(b"\xca\xfe\xba\xbe")
    gradle_out = root / "build"
    gradle_out.mkdir()
    (gradle_out / "leftover.txt").write_text("x", encoding="utf-8")
    return root


def test_source_package_named_build_is_copied(tmp_path):
    src = _make_repo(tmp_path / "repo")
    dest = _copy_repo(src, tmp_path / "copy")
    kept = dest / "src/main/java/org/apache/commons/io/build/AbstractOrigin.java"
    assert kept.exists(), "a source package named 'build' was dropped by the copy"


def test_build_output_next_to_a_pom_is_still_skipped(tmp_path):
    src = _make_repo(tmp_path / "repo")
    dest = _copy_repo(src, tmp_path / "copy")
    assert not (dest / "target").exists(), "module build output should not be copied"
    assert not (dest / "build").exists(), "root gradle output should not be copied"


def test_nested_module_output_is_skipped_but_nested_sources_survive(tmp_path):
    root = tmp_path / "repo"
    (root / "pom.xml").parent.mkdir(parents=True, exist_ok=True)
    (root / "pom.xml").write_text("<project/>", encoding="utf-8")
    mod = root / "core"
    (mod / "src/main/java/pkg/build").mkdir(parents=True)
    (mod / "pom.xml").write_text("<project/>", encoding="utf-8")
    (mod / "src/main/java/pkg/build/B.java").write_text(
        "package pkg.build;\npublic class B {}\n", encoding="utf-8")
    (mod / "target").mkdir()
    (mod / "target/x.jar").write_bytes(b"z")

    dest = _copy_repo(root, tmp_path / "copy")
    assert (dest / "core/src/main/java/pkg/build/B.java").exists()
    assert not (dest / "core/target").exists()
