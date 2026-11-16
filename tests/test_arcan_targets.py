"""Targets read from Arcan's package cycles, and dissolution judged by Arcan before and after."""
from dsarp.experiments.arcan_diff import cycle_clusters, cycles_dissolved


def table(d, cycles, packages=("a", "b", "c", "d", "e", "x")):
    """Arcan's packageCyclicDependencyTable.csv: one row per cycle, 1 marks a member."""
    d.mkdir(parents=True, exist_ok=True)
    rows = ["Cycle," + ",".join(packages)]
    rows += ["%d,%s" % (i, ",".join("1" if p in c else "0" for p in packages))
             for i, c in enumerate(cycles)]
    (d / "packageCyclicDependencyTable.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return d


def test_overlapping_cycles_form_one_target(tmp_path):
    # Commons Exec: {exec, launcher} and {exec, environment, launcher} are one tangle.
    a = table(tmp_path, [{"a", "b"}, {"a", "b", "c"}, {"d", "e"}])
    assert cycle_clusters(a) == [["d", "e"], ["a", "b", "c"]]


def test_dissolved_when_no_cycle_keeps_two_target_members(tmp_path):
    before = table(tmp_path / "b", [{"a", "b"}, {"a", "b", "c"}])
    after = table(tmp_path / "a", [{"c", "x"}])          # c still cycles, but with no other member
    r = cycles_dissolved(["a", "b", "c"], before, after)
    assert r["measured"] and r["in_before"] and r["dissolved"]
    assert r["added"] == [["c", "x"]]


def test_a_surviving_sub_cycle_is_not_dissolution(tmp_path):
    # The whole target no longer cycles as one, but {a, b} still does: the smell is still there.
    before = table(tmp_path / "b", [{"a", "b"}, {"a", "b", "c"}])
    after = table(tmp_path / "a", [{"a", "b"}])
    r = cycles_dissolved(["a", "b", "c"], before, after)
    assert not r["dissolved"]
    assert r["left"] == [["a", "b"]]


def test_a_cycle_moved_outside_the_target_still_counts(tmp_path):
    before = table(tmp_path / "b", [{"a", "b"}])
    after = table(tmp_path / "a", [{"a", "b", "x"}])
    assert not cycles_dissolved(["a", "b"], before, after)["dissolved"]


def test_no_table_after_is_unmeasured_not_dissolved(tmp_path):
    # Arcan writes the table even with zero cycles (header only), so a missing one means no run.
    before = table(tmp_path / "b", [{"a", "b"}])
    (tmp_path / "a").mkdir()
    r = cycles_dissolved(["a", "b"], before, tmp_path / "a")
    assert not r["measured"] and not r["dissolved"]


def test_header_only_table_is_zero_cycles(tmp_path):
    before = table(tmp_path / "b", [{"a", "b"}])
    after = table(tmp_path / "a", [])
    r = cycles_dissolved(["a", "b"], before, after)
    assert r["measured"] and r["dissolved"] and r["left"] == []


def test_planner_targets_come_from_arcan_when_asked(tmp_path):
    from dsarp.experiments.scc_dissolve import plan_targets
    a = table(tmp_path, [{"a", "b"}, {"a", "b", "c"}, {"d", "e"}])
    # jdeps alone would see one cycle, {x, y}; Arcan's clusters replace it, size cap and limit apply.
    edges = [("x.X", "y.Y"), ("y.Y", "x.X")]
    assert plan_targets(edges, max_size=15, limit=10, arcan_dir=a) == [{"d", "e"}, {"a", "b", "c"}]
    assert plan_targets(edges, max_size=2, limit=10, arcan_dir=a) == [{"d", "e"}]
    assert plan_targets(edges, max_size=15, limit=1, arcan_dir=a) == [{"d", "e"}]
    assert plan_targets(edges, max_size=15, limit=10) == [{"x", "y"}]


def test_a_target_arcan_never_saw_is_not_dissolved(tmp_path):
    before = table(tmp_path / "b", [{"d", "e"}])
    after = table(tmp_path / "a", [])
    r = cycles_dissolved(["a", "b"], before, after)
    assert not r["in_before"] and not r["dissolved"]
