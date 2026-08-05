"""Files that STAY need an import for a type that moves out from under them.

CASNumberCheckDigit stays in `routines` and refers to ModulusCheckDigit by simple name,
because they were neighbours. Move ModulusCheckDigit out and the bare name resolves to
nothing - which is why every Unstable Dependency and Scattered Functionality pass failed
with `cannot find symbol`.
"""
from dsarp.refactoring.strategies import imports_for_types_left_behind

PKG = "org.apache.commons.validator.routines"
NEW = "org.apache.commons.validator.routines.checkdigit.ModulusCheckDigit"


def _repo(tmp_path):
    d = tmp_path / "src/main/java/org/apache/commons/validator/routines"
    d.mkdir(parents=True)
    (d / "ModulusCheckDigit.java").write_text(
        f"package {PKG};\npublic class ModulusCheckDigit {{}}\n", encoding="utf-8")
    (d / "CASNumberCheckDigit.java").write_text(
        f"package {PKG};\npublic class CASNumberCheckDigit extends ModulusCheckDigit {{}}\n",
        encoding="utf-8")
    (d / "Unrelated.java").write_text(
        f"package {PKG};\npublic class Unrelated {{}}\n", encoding="utf-8")
    return tmp_path


def test_staying_file_that_uses_the_moved_type_gets_an_import(tmp_path):
    got = imports_for_types_left_behind(_repo(tmp_path), [(f"{PKG}.ModulusCheckDigit", NEW)])
    assert got.get(f"{PKG}.CASNumberCheckDigit") == [NEW]


def test_file_that_does_not_use_it_is_untouched(tmp_path):
    got = imports_for_types_left_behind(_repo(tmp_path), [(f"{PKG}.ModulusCheckDigit", NEW)])
    assert f"{PKG}.Unrelated" not in got


def test_the_moving_file_itself_is_not_given_an_import(tmp_path):
    got = imports_for_types_left_behind(_repo(tmp_path), [(f"{PKG}.ModulusCheckDigit", NEW)])
    assert f"{PKG}.ModulusCheckDigit" not in got


def test_a_move_inside_the_same_package_needs_nothing(tmp_path):
    same = f"{PKG}.RenamedCheckDigit"
    got = imports_for_types_left_behind(_repo(tmp_path), [(f"{PKG}.ModulusCheckDigit", same)])
    assert got == {}
