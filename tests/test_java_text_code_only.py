"""Locating a method body over raw Java is wrong in ways that cost a measurement."""
from dsarp.refactoring.java_text import body_range, code_only

# Designite reports this method as starting at line 1, the javadoc. The javadoc's {@code {}}
# braces balance, so counting braces from line 1 without stripping comments closes the "method"
# at line 3 and never sees the body -- which is how 12 literals got reported as absent from code
# they were sitting in.
JAVADOC_BRACES = """\
    /**
     * Scale by {@code 100} when the multiplier says so, see {@link #other()}.
     */
    protected int determineScale(final NumberFormat format) {
        if (multiplier == 100) { // CHECKSTYLE IGNORE MagicNumber
            scale += 2;
        }
        return scale;
    }
""".splitlines()


def test_a_body_is_located_past_its_javadoc_braces():
    lo, hi = body_range(JAVADOC_BRACES, 1)
    assert JAVADOC_BRACES[lo].strip().startswith("protected int determineScale")
    assert JAVADOC_BRACES[hi].strip() == "}"
    # the whole body, not the javadoc
    assert any("return scale;" in l for l in JAVADOC_BRACES[lo:hi + 1])


def test_the_literal_is_found_in_code_and_not_in_the_javadoc():
    lo, hi = body_range(JAVADOC_BRACES, 1)
    stripped = code_only(JAVADOC_BRACES[lo:hi + 1])
    assert any("100" in c for c in stripped), "the real literal was stripped away"
    # the javadoc's own 100 is above the body and must not be what matched
    assert "100" not in "".join(code_only(JAVADOC_BRACES[:3]))


def test_comments_and_literals_are_blanked_but_lines_still_line_up():
    src = ['int a = 1; // 999 in a comment',
           'String s = "literal 888 here";',
           "char c = '}';",
           '/* block 777',
           '   still block */ int b = 2;']
    out = code_only(src)
    assert len(out) == len(src)
    assert "999" not in out[0] and "1" in out[0]
    assert "888" not in out[1]
    # a brace inside a char literal must not count, or every balance downstream is wrong
    assert "}" not in out[2]
    assert "777" not in out[3]
    assert "int b = 2;" in out[4]


def test_an_escaped_quote_does_not_end_the_string_early():
    # If the backslash-quote were treated as closing the string, `42` would look like code.
    out = code_only([r'String s = "he said \" 42 \" to me"; int real = 7;'])
    assert "42" not in out[0]
    assert "7" in out[0]
