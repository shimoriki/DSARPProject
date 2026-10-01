"""The composite must place the class in a NEW package and leave the tree compilable.

Two expert refactorings in the Arcelli Fontana package do exactly this; moving methods alone
removed 0 of 5 package edges in the SWE-Refactor experiment, because a method move leaves the
class, and so the package, where it was.
"""
from pathlib import Path

from dsarp.refactoring.extract_to_package import apply, methods_reaching, plan
from dsarp.refactoring.strategies import SourceFacts

CONSUMER = """package com.app.web;

import com.app.core.Engine;
import com.app.web.Helper;

public class Builder {

    private int count;

    public static Engine buildEngine(String name) {
        return new Engine(name);
    }

    public static String describe(Engine e) {
        return "engine:" + e.name();
    }

    public int localOnly() {
        return count + Helper.pad(1);
    }
}
"""

HELPER = "package com.app.web;\n\npublic class Helper {\n    public static int pad(int x) { return x; }\n}\n"
ENGINE = "package com.app.core;\n\npublic class Engine {\n    private final String n;\n" \
         "    public Engine(String n) { this.n = n; }\n    public String name() { return n; }\n}\n"
CALLER = """package com.app.cli;

import com.app.web.Builder;

public class Main {
    public static void main(String[] a) {
        System.out.println(Builder.describe(Builder.buildEngine("x")));
    }
}
"""


def _repo(tmp_path):
    root = tmp_path / "src" / "main" / "java"
    for rel, text in (("com/app/web/Builder.java", CONSUMER),
                      ("com/app/web/Helper.java", HELPER),
                      ("com/app/core/Engine.java", ENGINE),
                      ("com/app/cli/Main.java", CALLER)):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


EDGE = {"from": "com.app.web", "to": "com.app.core",
        "carriers": ["com.app.web.Builder -> com.app.core.Engine"]}


def test_only_the_methods_that_reach_across_the_edge_are_selected(tmp_path):
    facts = SourceFacts(_repo(tmp_path))
    m = methods_reaching(facts, "com.app.web.Builder", "com.app.core")
    # buildEngine and describe name Engine; localOnly does not and must be left alone
    assert sorted(m) == ["buildEngine", "describe"]


def test_the_plan_targets_a_new_package_not_the_source_package(tmp_path):
    p = plan(SourceFacts(_repo(tmp_path)), EDGE)
    assert p is not None
    assert p["new_package"] == "com.app.web.support"
    assert p["target_class"] == "com.app.web.support.BuilderSupport"
    assert p["source_class"] == "com.app.web.Builder"
    # the criterion is stated conditionally, because one class may not be the only path
    assert "requires that these 2 method(s) were the only path" in p["success_criterion"]
    assert p["sole_carrier"] is True


def test_the_class_lands_under_the_new_package_directory(tmp_path):
    repo = _repo(tmp_path)
    p = plan(SourceFacts(repo), EDGE)
    r = apply(repo, p)
    assert r["ok"] and r["methods_moved"] == 2
    out = repo / "src/main/java/com/app/web/support/BuilderSupport.java"
    assert out.exists(), "written beside the source instead of under the new package"
    text = out.read_text(encoding="utf-8")
    assert text.startswith("package com.app.web.support;")
    assert "buildEngine" in text and "describe" in text
    # it referenced a package-mate of the original, which now needs an import
    assert "import com.app.core.Engine;" in text


def test_callers_are_repointed_and_given_an_import(tmp_path):
    repo = _repo(tmp_path)
    apply(repo, plan(SourceFacts(repo), EDGE))
    caller = (repo / "src/main/java/com/app/cli/Main.java").read_text(encoding="utf-8")
    assert "BuilderSupport.describe(" in caller and "BuilderSupport.buildEngine(" in caller
    assert "import com.app.web.support.BuilderSupport;" in caller


def test_the_source_keeps_what_did_not_reach_across(tmp_path):
    repo = _repo(tmp_path)
    apply(repo, plan(SourceFacts(repo), EDGE))
    src = (repo / "src/main/java/com/app/web/Builder.java").read_text(encoding="utf-8")
    # the instance method that never reached across stays, with its field
    assert "public int localOnly()" in src and "private int count;" in src
    # the moved declarations are gone, and the import of the new type is present
    assert "public static Engine buildEngine" not in src
    assert "public static String describe" not in src
    assert "import com.app.web.support.BuilderSupport;" in src


def test_a_class_with_nothing_reaching_across_is_not_planned(tmp_path):
    facts = SourceFacts(_repo(tmp_path))
    assert plan(facts, {"from": "com.app.web", "to": "com.app.cli",
                        "carriers": ["com.app.web.Builder -> com.app.cli.Main"]}) is None


def test_applying_twice_refuses_rather_than_overwriting(tmp_path):
    repo = _repo(tmp_path)
    p = plan(SourceFacts(repo), EDGE)
    assert apply(repo, p)["ok"]
    again = apply(repo, p)
    assert not again["ok"]


def test_the_result_actually_compiles(tmp_path):
    """Generated Java that parses in a regex and not in javac is the failure mode here.

    Every earlier source-surgery attempt in this project produced code that looked right and
    did not build: missing imports, a declaration cut in the wrong place, a call qualified
    where it should not have been.
    """
    import os
    import shutil
    import subprocess
    javac = shutil.which("javac")
    if not javac and os.environ.get("JAVA_HOME"):
        cand = Path(os.environ["JAVA_HOME"]) / "bin" / "javac.exe"
        javac = str(cand) if cand.exists() else None
    if not javac:
        import pytest
        pytest.skip("no javac on PATH or JAVA_HOME")

    repo = _repo(tmp_path)
    r = apply(repo, plan(SourceFacts(repo), EDGE))
    assert r["ok"]
    srcs = [str(p) for p in (repo / "src/main/java").rglob("*.java")]
    out = tmp_path / "classes"
    out.mkdir()
    proc = subprocess.run([javac, "-d", str(out), *srcs], capture_output=True, text=True,
                          timeout=300)
    assert proc.returncode == 0, "javac rejected the extracted code:\n" + proc.stderr
    # the new type is a real class in the new package, not just a file
    assert (out / "com/app/web/support/BuilderSupport.class").exists()


OVERLOADED = """package com.app.web;

import com.app.core.Engine;

public class Multi {

    public static Engine make(String n) {
        return new Engine(n);
    }

    public static Engine make(String n, int size) {
        return new Engine(n + size);
    }

    public static String label(Engine e) {
        return e.name();
    }
}
"""


def test_an_overloaded_method_is_not_extracted(tmp_path):
    """Cutting one overload and qualifying the name rewrites the other's DECLARATION.

    Measured on commons-validator: GenericValidator.isDate has two overloads, and the
    extraction produced `public static boolean GenericValidatorSupport.isDate(` -- javac
    reported "';' expected".
    """
    repo = _repo(tmp_path)
    p = repo / "src/main/java/com/app/web/Multi.java"
    p.write_text(OVERLOADED, encoding="utf-8")
    m = methods_reaching(SourceFacts(repo), "com.app.web.Multi", "com.app.core")
    assert "make" not in m, "overloaded method selected; its sibling declaration will break"
    assert m == ["label"]


OWN_MEMBER = """package com.app.web;

import com.app.core.Engine;

public class Uses {

    public static final String PREFIX = "p:";

    private static int tally;

    public static Engine named(String n) {
        tally++;
        return new Engine(PREFIX + n);
    }

    public static Engine plain(String n) {
        return new Engine(n);
    }
}
"""


def test_a_body_using_its_own_class_members_is_not_extracted(tmp_path):
    """Fine in the same package, "cannot find symbol" from a new one.

    log4j2's LogManager extraction compiled every call site and failed inside the new file,
    because the moved body named something its own class declared.
    """
    from dsarp.refactoring.extract_to_package import references_own_members
    repo = _repo(tmp_path)
    (repo / "src/main/java/com/app/web/Uses.java").write_text(OWN_MEMBER, encoding="utf-8")
    facts = SourceFacts(repo)
    m = methods_reaching(facts, "com.app.web.Uses", "com.app.core")
    # `named` touches PREFIX and tally; `plain` touches neither
    assert m == ["plain"], m
    hits = references_own_members(OWN_MEMBER, [OWN_MEMBER.split("public static Engine named")[1]
                                               .split("public static Engine plain")[0]], ["named"])
    assert "PREFIX" in hits and "tally" in hits


LOCALS = """package com.app.web;

import com.app.core.Engine;
import java.util.HashMap;
import java.util.Map;

public class Copier {

    private static final String TAG = "t";

    public static Map<String, Engine> copyAll(Map<String, Engine> in) {
        final Map<String, Engine> results = new HashMap<>(in.size());
        for (String k : in.keySet()) {
            results.put(k, in.get(k));
        }
        return results;
    }

    public static Engine tagged(Engine e) {
        return new Engine(TAG + e.name());
    }
}
"""


def test_a_local_variable_is_not_mistaken_for_a_field(tmp_path):
    """`final Map results = ...` inside a method is a local, not a member.

    At eight-space indentation the field pattern matched locals, and the guard refused
    commons-validator's ValidatorUtils -- the one candidate that had already compiled AND
    removed its targeted edge.
    """
    repo = _repo(tmp_path)
    (repo / "src/main/java/com/app/web/Copier.java").write_text(LOCALS, encoding="utf-8")
    m = methods_reaching(SourceFacts(repo), "com.app.web.Copier", "com.app.core")
    # copyAll declares a local called results and must stay eligible;
    # tagged reads the private constant TAG and must not.
    assert m == ["copyAll"], m
