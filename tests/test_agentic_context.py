from dsarp.agentic.context import build_context, render

EDGES = {("a.X", "b.Y"), ("b.Y", "a.Z"), ("b.W", "a.Z"), ("c.Q", "a.X")}


def test_context_keeps_only_cycle_edges():
    ctx = build_context(EDGES, {"a", "b"})
    assert ctx["packages"] == ["a", "b"]
    assert sorted(ctx["package_edges"]) == [["a", "b", 1], ["b", "a", 2]]
    assert ["c.Q", "a.X"] not in ctx["carriers"]


def test_context_caps_carriers_cheapest_edge_first():
    ctx = build_context(EDGES, {"a", "b"}, max_carriers=1)
    assert ctx["carriers"] == [["a.X", "b.Y"]]


def test_render_states_catalogue_and_feedback():
    text = render(build_context(EDGES, {"a", "b"}), feedback="moveClass a.Q: unknown class")
    assert "moveClass" in text and "invertEdge" in text and '"operations"' in text
    assert text.rstrip().endswith("moveClass a.Q: unknown class")
