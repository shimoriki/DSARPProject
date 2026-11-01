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
