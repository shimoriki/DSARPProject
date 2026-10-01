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
