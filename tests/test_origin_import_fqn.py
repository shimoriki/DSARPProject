"""A nested-type import must not suppress the import of its outer type.

Measured cost of getting this wrong: moving org.apache.tika.metadata.Metadata into
...metadata.writefilter needed `import org.apache.tika.metadata.Property;`, but the file already
carried `import org.apache.tika.metadata.Property.PropertyType;`. A substring test saw the longer
string, decided Property was already qualified, and skipped the import. 36 `cannot find symbol`
errors in that one file, tika-core failed, 91 further modules were skipped, and the Arcan run on
the result read 176 smells against a 260 baseline -- a number that looked like a 32% improvement
and was only a broken build.
"""
from dsarp.refactoring.java_text import names_fqn

PKG = "org.apache.tika.metadata"


def test_a_nested_import_does_not_count_as_qualifying_the_outer_type():
    text = "import %s.Property.PropertyType;\n" % PKG
    assert not names_fqn(text, PKG + ".Property"), \
        "a nested-type import was read as qualifying its outer type"


def test_a_real_qualified_use_does_count():
    assert names_fqn("    %s.Property p = null;\n" % PKG, PKG + ".Property")
    assert names_fqn("import %s.Property;\n" % PKG, PKG + ".Property")


def test_a_longer_sibling_name_does_not_match():
    # PropertyTypeException must not satisfy a search for Property
    text = "import %s.PropertyTypeException;\n" % PKG
    assert not names_fqn(text, PKG + ".Property")


def test_the_name_must_not_be_glued_to_an_identifier_or_a_parent_package():
    assert not names_fqn("import com.other.%s.Property;\n" % PKG, PKG + ".Property")
    assert not names_fqn("%s.PropertyX x;" % PKG, PKG + ".Property")


def test_the_exact_tika_file_header_still_needs_the_outer_import():
    header = (
        "package org.apache.tika.metadata.writefilter;\n"
        "import org.apache.tika.metadata.Property.PropertyType;\n"
        "import org.apache.tika.metadata.PropertyTypeException;\n"
        "public class Metadata {\n"
        "    private Property[] props;\n"
        "}\n")
    assert not names_fqn(header, PKG + ".Property"), "Property would be left unimported again"
    assert names_fqn(header, PKG + ".PropertyTypeException"), "this one IS already imported"
