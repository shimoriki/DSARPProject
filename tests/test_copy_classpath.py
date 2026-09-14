"""A working copy must lead back to its original, without touching the tree that gets built.

Precheck ran on the original repository and apply on a copy with no build output, so the two
modelled the module against different classpaths: 6 of 9 tika confirmation candidates were
called legal and then refused with "RTFTokenizer cannot be resolved to a type".
"""
from dsarp.verification.effect_checker import COPY_MARKER, _copy_repo, original_module


def test_copy_leads_back_to_its_original_module(tmp_path):
    mod = tmp_path / "orig" / "sub" / "mod"
    (mod / "src").mkdir(parents=True)
    # target/ only counts as build output beside a build file; without one it is a source
    # directory that happens to be called target, and must be copied.
    (mod / "pom.xml").write_text("<project/>", encoding="utf-8")
    (mod / "target" / "classes").mkdir(parents=True)
    (mod / "src" / "A.java").write_text("class A {}", encoding="utf-8")

    copy = _copy_repo(tmp_path / "orig", tmp_path / "work" / "copy")

    assert not (copy / "sub" / "mod" / "target").exists(), "build output must not be copied"
    assert not (copy / COPY_MARKER).exists(), "the marker must stay outside the built tree"
    assert original_module(copy / "sub" / "mod") == mod.resolve()


def test_a_directory_that_is_not_a_copy_has_no_original(tmp_path):
    (tmp_path / "plain").mkdir()
    assert original_module(tmp_path / "plain") is None
