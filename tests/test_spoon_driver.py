"""The Spoon driver actually moves a class, and the result still compiles.

The failure this guards is the one that looked like success for three iterations: Spoon
reparents the CtType but every CtTypeReference naming it keeps its own package reference, so
the file lands in the right directory, the package declaration is right, and callers in the
old package silently no longer resolve it. Only javac catches that, so javac is in the test.

Skipped when the driver jar or a JDK is missing — this is an integration check, not a reason
to fail the unit suite on a machine without Java.
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from dsarp.tools.spoon_runner import apply_edits, driver_built, java_exe

pytestmark = pytest.mark.skipif(
    not driver_built() or not java_exe() or not shutil.which("javac"),
    reason="needs the Spoon driver jar (mvn -f tools/dsarp-spoon/pom.xml package) and a JDK")


def test_move_class_relocates_and_still_compiles():
    repo = Path(tempfile.mkdtemp(prefix="spoon-drv-"))
    src = repo / "src" / "main" / "java"
    files = {
        "com/x/core/Engine.java":
            "package com.x.core;\n\n/** javadoc survives. */\n"
            "public class Engine {\n    public int run() { return 42; }\n}\n",
        # Caller sits in the OLD package and uses Engine with no import — after the move it
        # needs one, and nothing but a reference rewrite will give it one.
        "com/x/core/Caller.java":
            "package com.x.core;\n\npublic class Caller {\n"
            "    public int go() { return new Engine().run(); }\n}\n",
        "com/x/util/Helper.java": "package com.x.util;\n\npublic class Helper { }\n",
    }
    for rel, body in files.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    res = apply_edits(repo, [{"op": "moveClass", "type": "com.x.core.Engine",
                              "toPackage": "com.x.util"}],
                      source_roots=[str(Path("src/main/java"))])
    assert res.get("ok"), json.dumps(res)[:400]
    assert len(res["applied"]) == 1 and not res["skipped"]

    moved = src / "com/x/util/Engine.java"
    assert moved.exists(), "type did not land in the target package directory"
    assert not (src / "com/x/core/Engine.java").exists(), "stale file left behind"
    body = moved.read_text(encoding="utf-8")
    assert body.startswith("package com.x.util;")
    assert "javadoc survives" in body

    caller = (src / "com/x/core/Caller.java").read_text(encoding="utf-8")
    assert "import com.x.util.Engine;" in caller, "reference was not retargeted"

    out = repo / "out"
    out.mkdir()
    javac = subprocess.run(["javac", "-d", str(out), *[str(p) for p in src.rglob("*.java")]],
                           capture_output=True, text=True)
    assert javac.returncode == 0, javac.stderr[:600]


def test_precheck_refuses_a_move_that_only_breaks_tests():
    """A move can be legal for main source and illegal for tests.

    commons-validator found this: ISBNValidator moved routines -> routines.checkdigit, the
    main source compiled cleanly, Arcan measured 21 smells, and then testCompile failed with
    "ISBN10_REGEX is not public ... cannot be accessed from outside package". The precheck
    had called it legal because it only ever modelled src/main/java, so src/test/java was
    never parsed and the access was invisible.
    """
    from dsarp.tools.spoon_runner import precheck_edits

    repo = Path(tempfile.mkdtemp(prefix="spoon-test-vis-"))
    main = repo / "src" / "main" / "java" / "a"
    test = repo / "src" / "test" / "java" / "a"
    main.mkdir(parents=True)
    test.mkdir(parents=True)
    # SECRET is package-private, so only code in package `a` may read it.
    (main / "Thing.java").write_text(
        "package a;\npublic class Thing {\n    static final String SECRET = \"x\";\n}\n",
        encoding="utf-8")
    (main / "Other.java").write_text("package a;\npublic class Other { }\n", encoding="utf-8")
    # The test stays in `a` and reads that field. Moving Thing to `b` breaks it.
    (test / "ThingTest.java").write_text(
        "package a;\nclass ThingTest {\n    String s = Thing.SECRET;\n}\n", encoding="utf-8")

    edits = [{"op": "moveClass", "type": "a.Thing", "toPackage": "b"}]
    # A non-empty classpath is what turns the access checks on; these sources need no jars.
    res = precheck_edits(repo, edits, source_roots=["src/main/java"],
                         classpath=[str(repo)])
    illegal = res.get("illegal") or []
    assert not (res.get("legal") or []), f"should not be legal: {res}"
    assert len(illegal) == 1, res
    assert illegal[0].get("testsModelled") is True, "test sources were not modelled"
    assert "SECRET" in illegal[0]["why"], illegal[0]["why"]
    shutil.rmtree(repo, ignore_errors=True)
