from dsarp.refactoring import scc_planner as sp


def graph(*pairs):
    return set(pairs)


def test_components_are_smallest_first():
    pg = {("a", "b"), ("b", "a"), ("c", "d"), ("d", "e"), ("e", "c")}
    assert [len(c) for c in sp.components(pg)] == [2, 3]


def test_nested_classes_fold_into_their_owner():
    assert sp.top_level_edges([("p.A$1", "p.A"), ("p.A$1", "q.B$C")]) == {("p.A", "q.B")}


def test_one_move_dissolves_a_two_package_cycle():
    e = graph(("x.A", "y.B"), ("y.C", "x.A"), ("y.B", "y.C"))
    r = sp.plan(e, {"x", "y"})
    assert r["dissolves"] and len(r["moves"]) == 1


def test_a_move_set_is_found_when_one_move_is_not_enough():
    # Log4j2's shape: moving Layout alone leaves perf.State using it, and Defaults still ties
    # the new package back to the old one.
    e = graph(("j.Layout", "r.Res"), ("r.Res", "j.Layout"), ("r.Res", "j.Defaults"),
              ("j.State", "j.Layout"), ("j.Layout", "j.Defaults"))
    fixed = {"j.State"}
    r = sp.plan(e, {"j", "r"}, accept=lambda c, d: c not in fixed)
    assert r["dissolves"]


def test_refuses_a_plan_that_pulls_a_package_into_a_cycle():
    e = graph(("x.A", "y.B"), ("y.B", "x.A"), ("x.A", "z.C"), ("z.D", "y.B"))
    r = sp.plan(e, {"x", "y"}, accept=lambda c, d: False)
    assert r["moves"] == [] and not r["dissolves"]


NO_MOVES = lambda c, d: False
FREE = lambda p, i, m: None


def test_an_inversion_dissolves_where_no_move_is_accepted():
    e = graph(("x.A", "y.B"), ("y.B", "x.C"))
    r = sp.plan(e, {"x", "y"}, accept=NO_MOVES, inversions=[("x", "y.B")], blocked=FREE, sig=lambda i: set())
    assert r["dissolves"] and r["inversions"] == [["x", "y.B"]] and r["moves"] == []


def test_a_move_can_unblock_an_inversion():
    # Maker builds y.B in x, so the inversion holds only once Maker has left x.
    e = graph(("x.A", "y.B"), ("x.Maker", "y.B"), ("y.B", "x.C"))
    blocked = lambda p, i, m: None if m.get("x.Maker") else "constructed by x.Maker"
    r = sp.plan(e, {"x", "y"}, accept=lambda c, d: c == "x.Maker", inversions=[("x", "y.B")],
                blocked=blocked, sig=lambda i: set())
    assert r["dissolves"] and r["moves"] == [("x.Maker", "y")] and r["inversions"] == [["x", "y.B"]]


def test_a_type_in_the_interface_signature_keeps_the_edge():
    e = graph(("x.A", "y.B"), ("y.B", "x.C"), ("y.Foo", "y.B"))
    r = sp.plan(e, {"x", "y"}, accept=NO_MOVES, inversions=[("x", "y.B")], blocked=FREE,
                sig=lambda i: {"y.Foo"})
    assert not r["dissolves"]


def test_a_blocked_inversion_is_never_planned():
    e = graph(("x.A", "y.B"), ("y.B", "x.C"))
    r = sp.plan(e, {"x", "y"}, accept=NO_MOVES, inversions=[("x", "y.B")], blocked=lambda p, i, m: "no")
    assert not r["dissolves"] and r["inversions"] == []


def test_a_class_built_through_a_hidden_constructor_in_its_package_does_not_move(tmp_path):
    from dsarp.experiments.scc_dissolve import _hidden_ctor_used
    from dsarp.refactoring.strategies import SourceFacts
    files = {"src/main/java/a/Meta.java": "package a;\npublic class Meta {\n    protected Meta() {}\n}\n",
             "src/test/java/a/MetaTest.java": "package a;\nclass MetaTest { Meta m = new Meta(); }\n",
             "src/main/java/a/Open.java": "package a;\npublic class Open {\n    public Open() {}\n}\n",
             "src/main/java/a/User.java": "package a;\nclass User { Open o = new Open(); }\n"}
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    facts = SourceFacts(tmp_path)
    assert _hidden_ctor_used(facts, "a.Meta") and not _hidden_ctor_used(facts, "a.Open")


def test_a_public_class_does_not_move_into_a_private_package(tmp_path):
    from dsarp.experiments.scc_dissolve import _into_private
    from dsarp.refactoring.strategies import SourceFacts
    for rel, text in {"src/main/java/a/io/Api.java": "package a.io;\npublic final class Api {}\n",
                      "src/main/java/a/io/Hid.java": "package a.io;\nclass Hid {}\n",
                      "src/main/java/a/io/internal/In.java": "package a.io.internal;\npublic class In {}\n"}.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    f = SourceFacts(tmp_path)
    assert _into_private(f, "a.io.Api", "a.io.internal")
    assert not _into_private(f, "a.io.Hid", "a.io.internal")        # not API
    assert not _into_private(f, "a.io.internal.In", "a.impl")       # already private
    assert not _into_private(f, "a.io.Api", "a.util")


def test_only_skipped_modules_with_tests_make_a_run_partial(tmp_path):
    from dsarp.tools.arcan_runner import modules_with_tests
    poms = {"core": "<project><parent><name>Root</name></parent><name>Core</name></project>",
            "dist": "<project><name>Dist</name></project>",
            "odd": "<project><name>${project.artifactId}</name></project>"}
    for d, pom in poms.items():
        (tmp_path / d).mkdir()
        (tmp_path / d / "pom.xml").write_text(pom, encoding="utf-8")
    (tmp_path / "core/src/test/java/a").mkdir(parents=True)
    (tmp_path / "core/src/test/java/a/T.java").write_text("class T {}", encoding="utf-8")
    assert modules_with_tests(tmp_path) == {"Core": True, "Dist": False}   # odd: unnamed, assumed tested


def test_level_requires_passing_tests():
    assert sp.level({"a", "b"}, [{"a", "b"}], [], 1, "INVALID", True) == "2"


def test_level_4c_needs_the_detector_to_agree():
    assert sp.level({"a", "b"}, [{"a", "b"}], [], 1, "PASS", True) == "4c"
    assert sp.level({"a", "b"}, [{"a", "b"}], [], 1, "PASS", False) == "4b"


def test_shrunk_cycle_is_4b_and_named_edge_is_4a():
    assert sp.level({"a", "b", "c"}, [{"a", "b", "c"}], [{"a", "b"}], 1, "PASS", False) == "4b"
    assert sp.level({"a", "b"}, [{"a", "b"}], [{"a", "b"}], 1, "PASS", False) == "4a"


def test_service_files_are_read_without_comments(tmp_path):
    from dsarp.refactoring.name_refs import service_providers
    d = tmp_path / "m/src/main/resources/META-INF/services"
    d.mkdir(parents=True)
    (d / "a.Svc").write_text("# header\nb.One\nb.Two # note\n", encoding="utf-8")
    assert list(service_providers(tmp_path).values()) == [["b.One", "b.Two"]]


def test_japicmp_output_keeps_only_incompatible_lines():
    from dsarp.tools.api_runner import incompatibilities
    assert incompatibilities("Comparing old\n---! REMOVED CLASS: a.B\n*** MODIFIED CLASS: c.D\n") \
        == ["---! REMOVED CLASS: a.B"]


def test_regression_rule_names_both_packages():
    from dsarp.tools.archunit_runner import regression_rule
    assert '"a"' in regression_rule("a", "b") and '"b"' in regression_rule("a", "b")


def test_a_new_cycle_blocks_success():
    assert sp.level({"a", "b"}, [{"a", "b"}], [{"c", "d"}], 1, "PASS", True) == "3"


def test_a_flake_may_reject_but_never_accept():
    from dsarp.verification.gates import settle_flakes
    v = {"ok": False, "state": "FAIL", "newly_failing": ["a#t"], "tests_not_run": 0}
    ok, bad, gone = {"a#t": "passed"}, {"a#t": "failure"}, {}
    assert settle_flakes(v, [ok] * 3, [ok] * 3)["state"] == "PASS"
    assert settle_flakes(v, [bad, ok, ok], [ok, bad, ok])["state"] == "PASS"
    assert settle_flakes(v, [ok] * 3, [ok, ok, bad])["state"] == "FAIL"
    assert settle_flakes(v, [ok] * 3, [gone] * 3)["state"] == "FAIL"
    assert settle_flakes({**v, "tests_not_run": 1}, [ok] * 3, [ok] * 3)["state"] == "FAIL"


def test_a_later_pass_does_not_hide_a_failed_run_of_the_same_id(tmp_path):
    from dsarp.tools.arcan_runner import surefire_outcomes
    d = tmp_path / "target/surefire-reports"
    d.mkdir(parents=True)
    (d / "TEST-a.xml").write_text('<testsuite><testcase classname="a" name="t"><failure/></testcase>'
                                  '<testcase classname="a" name="t"/></testsuite>', encoding="utf-8")
    assert surefire_outcomes(tmp_path) == {"a#t": "failure"}


def test_rewrite_names_leaves_longer_names_alone(tmp_path):
    from dsarp.refactoring.name_refs import rewrite_names
    f = tmp_path / "rules.xml"
    f.write_text("<a c='p.Arg'/><a c='p.ArgList'/>", encoding="utf-8")
    assert rewrite_names(tmp_path, {"p.Arg": "q.Arg"}) == ["rules.xml"]
    assert f.read_text(encoding="utf-8") == "<a c='q.Arg'/><a c='p.ArgList'/>"


def test_modules_are_found_at_the_root_and_nested(tmp_path):
    from dsarp.experiments.scc_dissolve import _modules
    (tmp_path / "target/classes").mkdir(parents=True)
    (tmp_path / "a/b/target/classes").mkdir(parents=True)
    changed = [tmp_path / "src/main/java/X.java", tmp_path / "a/b/src/Y.java"]
    assert _modules(changed, tmp_path, tmp_path / "other") == [".", "a/b"]


def test_illegal_xml_in_a_report_does_not_hide_its_tests(tmp_path):
    from dsarp.tools.arcan_runner import surefire_outcomes
    d = tmp_path / "target/surefire-reports"
    d.mkdir(parents=True)
    (d / "TEST-a.xml").write_text('<testsuite><testcase classname="a" name="t">'
                                  '<failure>bad &#xfffe; ￾</failure></testcase>'
                                  '<testcase classname="a" name="u"/></testsuite>', encoding="utf-8")
    assert surefire_outcomes(tmp_path) == {"a#t": "failure", "a#u": "passed"}


def test_release_history_is_neither_rewritten_nor_a_residual(tmp_path):
    from dsarp.refactoring.name_refs import residual, rewrite_names
    notes = tmp_path / "RELEASE-NOTES.txt"
    notes.write_text("o p.Arg was added", encoding="utf-8")
    (tmp_path / "changes.xml").write_text("<a>p.Arg</a>", encoding="utf-8")
    assert rewrite_names(tmp_path, {"p.Arg": "q.Arg"}) == []
    assert residual(tmp_path, "p.Arg")["ok"]


def test_a_partial_baseline_cannot_be_frozen():
    from dsarp.experiments.scc_dissolve import cannot_freeze
    assert cannot_freeze({"partial": False}) is None
    assert "m" in cannot_freeze({"partial": True, "skipped_modules": ["m"]})
    assert cannot_freeze(None)


def test_a_multi_move_row_can_head_a_patch():
    from dsarp.experiments.scc_dissolve import _patch_row
    row = _patch_row({"before_apply": [{"ok": True}, {"why": "reflective"}]}, [["a.B", "c"], ["a.D", "c"]])
    assert row["before_apply"] == {"why": "reflective"} and row["type"] == "a.B, a.D"
