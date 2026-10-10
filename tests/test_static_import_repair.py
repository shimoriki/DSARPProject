"""A moved type takes its static member imports with it, or the members stop resolving.

OpenRewrite's ChangeType repoints a plain `import a.b.Type` when Type moves. A static member
import of that type is removed outright instead. Measured on Tika: moving TikaCoreProperties cost
ParserUtils its `import static ...TikaCoreProperties.EMBEDDED_EXCEPTION;`, and the single line
using EMBEDDED_EXCEPTION failed with `cannot find symbol`, taking tika-core and 91 further
modules with it.
"""
from dsarp.refactoring.java_text import repair_static_imports

OLD = "org.apache.tika.metadata.TikaCoreProperties"
NEW = "org.apache.tika.metadata.writefilter.TikaCoreProperties"

BEFORE = """\
package org.apache.tika.utils;

import static org.apache.tika.metadata.TikaCoreProperties.EMBEDDED_EXCEPTION;
import org.apache.tika.metadata.TikaCoreProperties;

public class ParserUtils {
    void f(Metadata m) { m.add(EMBEDDED_EXCEPTION, "x"); }
}
"""
# what ChangeType leaves: the plain import repointed, the static one simply gone
AFTER = """\
package org.apache.tika.utils;

import org.apache.tika.metadata.writefilter.TikaCoreProperties;

public class ParserUtils {
    void f(Metadata m) { m.add(EMBEDDED_EXCEPTION, "x"); }
}
"""


def _tree(tmp_path, name, text_before, text_after):
    a = tmp_path / "before" / "src" / "main" / "java" / "p"
    b = tmp_path / "after" / "src" / "main" / "java" / "p"
    a.mkdir(parents=True); b.mkdir(parents=True)
    (a / name).write_text(text_before, encoding="utf-8")
    (b / name).write_text(text_after, encoding="utf-8")
    return tmp_path / "before", tmp_path / "after", b / name


def test_the_dropped_static_import_is_restored_at_the_new_package(tmp_path):
    before, after, f = _tree(tmp_path, "ParserUtils.java", BEFORE, AFTER)
    added = repair_static_imports(before, after, [(OLD, NEW)])
    assert added, "nothing was repaired"
    text = f.read_text(encoding="utf-8")
    assert "import static " + NEW + ".EMBEDDED_EXCEPTION;" in text
    assert "import static " + OLD + ".EMBEDDED_EXCEPTION;" not in text


def test_a_file_that_kept_its_static_import_is_left_alone(tmp_path):
    kept = AFTER.replace("import org.apache.tika.metadata.writefilter.TikaCoreProperties;",
                         "import static " + NEW + ".EMBEDDED_EXCEPTION;")
    before, after, f = _tree(tmp_path, "Ok.java", BEFORE, kept)
    assert repair_static_imports(before, after, [(OLD, NEW)]) == {}
    assert f.read_text(encoding="utf-8").count("import static") == 1


def test_a_static_import_of_an_unmoved_type_is_not_touched(tmp_path):
    src = BEFORE.replace(OLD + ".EMBEDDED_EXCEPTION", "org.other.Untouched.CONST")
    before, after, f = _tree(tmp_path, "Other.java", src, src)
    assert repair_static_imports(before, after, [(OLD, NEW)]) == {}


def test_no_moves_means_no_work(tmp_path):
    before, after, _ = _tree(tmp_path, "X.java", BEFORE, AFTER)
    assert repair_static_imports(before, after, []) == {}
