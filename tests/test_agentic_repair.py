from tests.conftest import Scripted
from dsarp.agentic.repair import apply_edits, error_summary, repair


def test_error_summary_keeps_java_errors_only():
    log = "[INFO] x\n[ERROR] /c/p/src/main/java/a/X.java:[3,8] cannot find symbol\n[ERROR] BUILD FAILURE\n"
    assert error_summary(log) == ["[ERROR] /c/p/src/main/java/a/X.java:[3,8] cannot find symbol"]


def test_edits_outside_scope_are_refused(tmp_path):
    for rel in ("src/main/java/a/X.java", "src/test/java/a/XTest.java", "pom.xml"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True); (tmp_path / rel).write_text("import b.Y;\n")
    allowed = {"src/main/java/a/X.java", "src/test/java/a/XTest.java", "pom.xml"}
    res = apply_edits(tmp_path, [{"path": p, "search": "import b.Y;", "replace": "import a.Y;"} for p in sorted(allowed)], allowed)
    assert res["applied"] == ["src/main/java/a/X.java"]
    assert sorted(r[1] for r in res["refused"]) == ["build file", "test source"]


def test_search_must_match_exactly_once(tmp_path):
    f = tmp_path / "X.java"; f.write_text("a; a;")
    res = apply_edits(tmp_path, [{"path": "X.java", "search": "a;", "replace": "b;"},
                                 {"path": "X.java", "search": "zz", "replace": "b"}], {"X.java"})
    assert [r[1] for r in res["refused"]] == ["search matched 2 times", "search matched 0 times"]


def test_reflective_workaround_refused(tmp_path):
    (tmp_path / "X.java").write_text("new Y();")
    res = apply_edits(tmp_path, [{"path": "X.java", "search": "new Y();",
                                  "replace": 'Class.forName("b.Y").newInstance();'}], {"X.java"})
    assert res["refused"] == [["X.java", "adds a reflective lookup"]]


def test_non_utf8_file_is_refused_not_raised(tmp_path):
    (tmp_path / "X.java").write_bytes("// Jörg\nbad".encode("latin-1"))
    res = apply_edits(tmp_path, [{"path": "X.java", "search": "bad", "replace": "good"}], {"X.java"})
    assert res["refused"] == [["X.java", "not utf-8"]]


def test_repair_stops_on_success_and_on_budget(tmp_path):
    (tmp_path / "X.java").write_text("bad")
    fix = '{"edits":[{"path":"X.java","search":"bad","replace":"good"}]}'
    ok = repair(Scripted(fix), tmp_path, {"X.java"}, "[ERROR] X.java bad",
                lambda: {"ok": (tmp_path / "X.java").read_text() == "good", "log": ""}, budget=5)
    assert ok["ok"] and len(ok["rounds"]) == 1 and ok["edited"] == ["X.java"]
    never = repair(Scripted(*["{}"] * 2), tmp_path, {"X.java"}, "e", lambda: {"ok": False, "log": "e"}, budget=2)
    assert not never["ok"] and len(never["rounds"]) == 2
