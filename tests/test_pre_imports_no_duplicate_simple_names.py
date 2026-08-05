"""Java allows one single-type-import per simple name.

apply_pre_imports checked only for the exact import string, so it would add
`a.b.ISBNValidator` to a file that already imported `x.y.ISBNValidator`. javac rejects that
file outright - which is why every God Component pass on commons-validator broke the build
while the plan itself was sound.
"""
from dsarp.refactoring.strategies import apply_pre_imports


def _write(tmp_path, body):
    f = tmp_path / "org/apache/commons/validator/CheckDigit.java"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body, encoding="utf-8")
    return f


FQN = "org.apache.commons.validator.CheckDigit"


def test_conflicting_simple_name_is_not_imported(tmp_path):
    f = _write(tmp_path, "package org.apache.commons.validator;\n"
                         "import org.apache.commons.validator.routines.ISBNValidator;\n"
                         "public class CheckDigit {}\n")
    apply_pre_imports(tmp_path, {FQN: ["org.apache.commons.validator.other.ISBNValidator"]})
    text = f.read_text(encoding="utf-8")
    assert text.count("ISBNValidator;") == 1, "a duplicate simple-name import was added"


def test_same_package_sibling_is_not_imported(tmp_path):
    f = _write(tmp_path, "package org.apache.commons.validator;\n"
                         "public class CheckDigit {}\n")
    apply_pre_imports(tmp_path, {FQN: ["org.apache.commons.validator.Sibling"]})
    assert "import org.apache.commons.validator.Sibling;" not in f.read_text(encoding="utf-8")


def test_a_genuinely_needed_import_is_still_added(tmp_path):
    f = _write(tmp_path, "package org.apache.commons.validator;\n"
                         "public class CheckDigit {}\n")
    apply_pre_imports(tmp_path, {FQN: ["org.apache.commons.validator.routines.Helper"]})
    assert "import org.apache.commons.validator.routines.Helper;" in f.read_text(encoding="utf-8")


def test_two_siblings_sharing_a_simple_name_yield_one_import(tmp_path):
    f = _write(tmp_path, "package org.apache.commons.validator;\n"
                         "public class CheckDigit {}\n")
    apply_pre_imports(tmp_path, {FQN: ["a.b.Thing", "c.d.Thing"]})
    assert f.read_text(encoding="utf-8").count("import ") == 1
