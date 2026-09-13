"""Extract Interface with Dependency Inversion actually breaks a package cycle.

moveClass can only cut a cycle when ONE class is the entire bridge between two packages.
Measured over 73 candidates across four repositories, 70 targeted a Cyclic Dependency and 59
changed nothing, because that condition almost never holds. DIP inverts the edge instead:
the CONSUMER package owns the abstraction, the implementation implements it, and the
consumer -> implementation edge disappears.

javac is in the test for the same reason it is in the move test: a transformation that looks
right in the model and does not compile has failed, and only the compiler can say so.
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from dsarp.tools.spoon_runner import apply_edits, driver_built, java_exe, precheck_edits

pytestmark = pytest.mark.skipif(
    not driver_built() or not java_exe() or not shutil.which("javac"),
    reason="needs the Spoon driver jar and a JDK")

# app -> engine (app calls Engine.run) and engine -> app (Engine holds an app.Config).
# A textbook two-package cycle.
CYCLE = {
    "com/x/engine/Engine.java":
        "package com.x.engine;\n\nimport com.x.app.Config;\n\n"
        "public class Engine {\n"
        "    private final Config cfg;\n"
        "    public Engine(Config cfg) { this.cfg = cfg; }\n"
        "    /** javadoc survives. */\n"
        "    public int run(int times) { return times * cfg.factor(); }\n"
        "    public String name() { return \"engine\"; }\n"
        "    int internal() { return 1; }\n"
        "}\n",
    "com/x/app/Config.java":
        "package com.x.app;\n\npublic class Config {\n"
        "    public int factor() { return 3; }\n}\n",
    "com/x/app/Runner.java":
        "package com.x.app;\n\nimport com.x.engine.Engine;\n\n"
        "public class Runner {\n"
        "    private Engine engine;\n"
        "    public void setEngine(Engine e) { this.engine = e; }\n"
        "    public int go() { return engine.run(2); }\n"
        "}\n",
}


def _repo(files):
    repo = Path(tempfile.mkdtemp(prefix="spoon-dip-"))
    for rel, body in files.items():
        f = repo / "src" / "main" / "java" / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")
    return repo


def _javac(repo):
    srcs = [str(p) for p in (repo / "src" / "main" / "java").rglob("*.java")]
    out = repo / "classes"
    out.mkdir(exist_ok=True)
    return subprocess.run(["javac", "-d", str(out), *srcs],
                          capture_output=True, text=True)


def test_extract_interface_inverts_the_dependency_and_compiles():
    repo = _repo(CYCLE)
    assert _javac(repo).returncode == 0, "fixture must compile before we touch it"

    edit = {"op": "extractInterface", "type": "com.x.engine.Engine",
            "toPackage": "com.x.app", "interfaceName": "EngineApi"}
    res = apply_edits(repo, [edit], source_roots=["src/main/java"],
                      classpath=[str(repo / "classes")])
    assert res.get("applied"), f"not applied: {json.dumps(res)[:900]}"

    src = repo / "src" / "main" / "java"
    iface = src / "com" / "x" / "app" / "EngineApi.java"
    assert iface.exists(), "the interface must be created in the CONSUMER package"
    itxt = iface.read_text(encoding="utf-8")
    assert "interface EngineApi" in itxt
    # Only what the consumer actually calls. name() and internal() are not used by app.
    assert "run(" in itxt, itxt
    assert "name(" not in itxt, "interface carries methods the consumer never calls"
    assert "internal(" not in itxt, "package-private method must never reach the interface"

    engine = (src / "com" / "x" / "engine" / "Engine.java").read_text(encoding="utf-8")
    assert "implements" in engine and "EngineApi" in engine, engine

    runner = (src / "com" / "x" / "app" / "Runner.java").read_text(encoding="utf-8")
    assert "EngineApi" in runner, runner
    # The point of the whole exercise: the consumer no longer names the engine package.
    assert "com.x.engine" not in runner, f"consumer still depends on engine:\n{runner}"

    r = _javac(repo)
    assert r.returncode == 0, f"refactored source does not compile:\n{r.stdout}\n{r.stderr}"
    shutil.rmtree(repo, ignore_errors=True)


def test_construction_is_not_a_blocker_under_type_constraints():
    """`Iface x = new Impl()` is legal Java, and the checklist refused it anyway.

    Refusing construction cost 16 of 44 pdfbox candidates. A declaration's type changing says
    nothing about what is assigned into it -- which is what a constraint system knows and a
    checklist cannot express. The initialiser keeps the concrete class, and the old import
    stays because something still names it.
    """
    files = dict(TWO_CLASS_CYCLE)
    files["com/x/app/Runner.java"] = 'package com.x.app;\n\nimport com.x.engine.Engine;\nimport com.x.engine.Meter;\n\npublic class Runner {\n    private Engine engine;\n    private Meter meter = new Meter();\n    public void wire(Engine e) { this.engine = e; }\n    public int go() { return engine.run(2) + meter.read(); }\n}\n'
    repo = _repo(files)
    assert _javac(repo).returncode == 0
    res = apply_edits(repo, [{"op": "invertEdge", "type": "com.x.engine.Engine",
                              "toPackage": "com.x.app",
                              "types": ["com.x.engine.Engine", "com.x.engine.Meter"]}],
                      source_roots=["src/main/java"], classpath=[str(repo / "classes")])
    assert res.get("applied"), res
    assert res["applied"][0]["classesInverted"] == 2, res["applied"][0]
    runner = (repo / "src/main/java/com/x/app/Runner.java").read_text(encoding="utf-8")
    assert "private MeterApi meter = new Meter();" in runner, runner
    assert "import com.x.engine.Meter;" in runner, "the constructor still needs its import"
    shutil.rmtree(repo / "classes", ignore_errors=True)
    r = _javac(repo)
    assert r.returncode == 0, "must compile: " + r.stderr
    shutil.rmtree(repo, ignore_errors=True)


def test_static_access_through_the_type_does_not_block_declarations():
    """`Engine.VERSION` keeps working: the class still exists, it just gained an interface.

    The checklist blocked the whole candidate on any static use anywhere. Constraints ask
    whether a DECLARATION can move, and a static read through the type name is not one.
    """
    files = dict(TWO_CLASS_CYCLE)
    files["com/x/engine/Engine.java"] = 'package com.x.engine;\n\nimport com.x.app.Config;\n\npublic class Engine {\n    public static final int VERSION = 2;\n    private final Config cfg;\n    public Engine(Config cfg) { this.cfg = cfg; }\n    public int run(int times) { return times * cfg.factor(); }\n}\n'
    files["com/x/app/Runner.java"] = 'package com.x.app;\n\nimport com.x.engine.Engine;\n\npublic class Runner {\n    private Engine engine;\n    public void wire(Engine e) { this.engine = e; }\n    public int go() { return engine.run(2) + Engine.VERSION; }\n}\n'
    repo = _repo(files)
    assert _javac(repo).returncode == 0
    res = apply_edits(repo, [{"op": "extractInterface", "type": "com.x.engine.Engine",
                              "toPackage": "com.x.app", "interfaceName": "EngineApi"}],
                      source_roots=["src/main/java"], classpath=[str(repo / "classes")])
    assert res.get("applied"), res
    runner = (repo / "src/main/java/com/x/app/Runner.java").read_text(encoding="utf-8")
    assert "private EngineApi engine;" in runner, runner
    assert "Engine.VERSION" in runner, "the static read must survive untouched"
    shutil.rmtree(repo / "classes", ignore_errors=True)
    r = _javac(repo)
    assert r.returncode == 0, "must compile: " + r.stderr
    shutil.rmtree(repo, ignore_errors=True)


def test_precheck_refuses_when_the_consumer_calls_nothing():
    files = dict(CYCLE)
    files["com/x/app/Runner.java"] = (
        "package com.x.app;\n\nimport com.x.engine.Engine;\n\n"
        "public class Runner {\n    private Engine engine;\n}\n")
    repo = _repo(files)
    res = precheck_edits(repo, [{"op": "extractInterface", "type": "com.x.engine.Engine",
                                 "toPackage": "com.x.app"}],
                         source_roots=["src/main/java"], classpath=[str(repo)])
    assert not (res.get("legal") or []), res
    why = res["illegal"][0]["why"]
    assert "no instance method" in why or "nothing to abstract" in why, why
    shutil.rmtree(repo, ignore_errors=True)


# A cycle the SINGLE-class inversion provably cannot close: app names TWO classes in engine.
# Measured on pdfbox, this is the common shape -- only 3 of 8 legal candidates had a consumer
# naming exactly one class across the boundary; the rest named 2, 2, 3, 5 and 25.
TWO_CLASS_CYCLE = {
    "com/x/engine/Engine.java":
        "package com.x.engine;\n\nimport com.x.app.Config;\n\n"
        "public class Engine {\n"
        "    private final Config cfg;\n"
        "    public Engine(Config cfg) { this.cfg = cfg; }\n"
        "    public int run(int times) { return times * cfg.factor(); }\n}\n",
    "com/x/engine/Meter.java":
        "package com.x.engine;\n\npublic class Meter {\n"
        "    public int read() { return 7; }\n}\n",
    "com/x/app/Config.java":
        "package com.x.app;\n\npublic class Config {\n"
        "    public int factor() { return 3; }\n}\n",
    "com/x/app/Runner.java":
        "package com.x.app;\n\nimport com.x.engine.Engine;\nimport com.x.engine.Meter;\n\n"
        "public class Runner {\n"
        "    private Engine engine;\n"
        "    private Meter meter;\n"
        "    public void wire(Engine e, Meter m) { this.engine = e; this.meter = m; }\n"
        "    public int go() { return engine.run(2) + meter.read(); }\n}\n",
}


def test_inverting_one_class_leaves_the_package_edge():
    """The finding that motivated group inversion, pinned as a test."""
    repo = _repo(TWO_CLASS_CYCLE)
    assert _javac(repo).returncode == 0
    res = apply_edits(repo, [{"op": "extractInterface", "type": "com.x.engine.Engine",
                              "toPackage": "com.x.app", "interfaceName": "EngineApi"}],
                      source_roots=["src/main/java"], classpath=[str(repo / "classes")])
    assert res.get("applied"), res
    runner = (repo / "src/main/java/com/x/app/Runner.java").read_text(encoding="utf-8")
    # Engine is abstracted, but Meter still drags the app -> engine edge along with it.
    assert "EngineApi" in runner
    assert "com.x.engine" in runner, "the edge should still be here — that is the point"
    assert _javac(repo).returncode == 0
    shutil.rmtree(repo, ignore_errors=True)


def test_invert_edge_removes_the_package_dependency_entirely():
    repo = _repo(TWO_CLASS_CYCLE)
    assert _javac(repo).returncode == 0

    edit = {"op": "invertEdge", "type": "com.x.engine.Engine", "toPackage": "com.x.app",
            "types": ["com.x.engine.Engine", "com.x.engine.Meter"]}
    res = apply_edits(repo, [edit], source_roots=["src/main/java"],
                      classpath=[str(repo / "classes")])
    assert res.get("applied"), f"not applied: {json.dumps(res)[:900]}"
    a = res["applied"][0]
    assert a["classesInverted"] == 2, a

    src = repo / "src" / "main" / "java"
    for name in ("EngineApi", "MeterApi"):
        assert (src / "com" / "x" / "app" / f"{name}.java").exists(), f"{name} missing"

    runner = (src / "com" / "x" / "app" / "Runner.java").read_text(encoding="utf-8")
    assert "EngineApi" in runner and "MeterApi" in runner, runner
    # The whole point: the consumer no longer names the implementation package at all.
    assert "com.x.engine" not in runner, f"edge survived:\n{runner}"

    for impl in ("Engine", "Meter"):
        body = (src / "com" / "x" / "engine" / f"{impl}.java").read_text(encoding="utf-8")
        assert f"class {impl} implements {impl}Api" in body, body

    r = _javac(repo)
    assert r.returncode == 0, f"does not compile:\n{r.stdout}\n{r.stderr}"
    shutil.rmtree(repo, ignore_errors=True)


def test_invert_edge_applies_the_legal_subset_of_a_group():
    """A field read blocks that one type; the rest of the group still goes through.

    Construction stopped being a blocker once constraints replaced the checklist, so the
    partial case is shown with a field read -- which an interface genuinely cannot declare, at
    any level of analysis.
    """
    files = dict(TWO_CLASS_CYCLE)
    files["com/x/engine/Meter.java"] = 'package com.x.engine;\n\npublic class Meter {\n    public int reading = 7;\n    public int read() { return reading; }\n}\n'
    files["com/x/app/Runner.java"] = 'package com.x.app;\n\nimport com.x.engine.Engine;\nimport com.x.engine.Meter;\n\npublic class Runner {\n    private Engine engine;\n    private Meter meter;\n    public void wire(Engine e, Meter m) { this.engine = e; this.meter = m; }\n    public int go() { return engine.run(2) + meter.reading; }\n}\n'
    repo = _repo(files)
    assert _javac(repo).returncode == 0
    res = apply_edits(repo, [{"op": "invertEdge", "type": "com.x.engine.Engine",
                              "toPackage": "com.x.app",
                              "types": ["com.x.engine.Engine", "com.x.engine.Meter"]}],
                      source_roots=["src/main/java"], classpath=[str(repo / "classes")])
    assert res.get("applied"), res
    a = res["applied"][0]
    assert a["classesInverted"] == 1, a
    assert a["classesSkipped"] == 1, a
    assert "field" in " ".join(a["skippedInGroup"]).lower(), a["skippedInGroup"]
    src = repo / "src" / "main" / "java"
    assert (src / "com" / "x" / "app" / "EngineApi.java").exists()
    assert not (src / "com" / "x" / "app" / "MeterApi.java").exists()
    shutil.rmtree(repo / "classes", ignore_errors=True)
    r = _javac(repo)
    assert r.returncode == 0, "partial inversion must still compile: " + r.stderr
    shutil.rmtree(repo, ignore_errors=True)
