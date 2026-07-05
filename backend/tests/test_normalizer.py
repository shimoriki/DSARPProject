from dsarp import services


def _seed(ctx, tmp_path):
    services.add_project(ctx, "demo", architecture_type="package-based-java")
    arcan_csv = tmp_path / "smells.csv"
    arcan_csv.write_text(
        "ID,SmellType,AffectedElements,Severity,Size,ATDI\n"
        "CD_1,cyclicDep,a.pkg;b.pkg,high,2,0.7\n", encoding="utf-8")
    edges_csv = tmp_path / "edges.csv"
    edges_csv.write_text("from,to,weight\na.pkg,b.pkg,4\nb.pkg,a.pkg,1\n",
                         encoding="utf-8")
    designite_csv = tmp_path / "designite.csv"
    designite_csv.write_text(
        'Project Name,Package Name,Architecture Smell,Cause of the Smell\n'
        'demo,a.pkg,Cyclic Dependency,"Participates in a dependency cycle with: b.pkg"\n',
        encoding="utf-8")
    services.import_tool_file(ctx, "demo", "arcan", str(arcan_csv))
    services.import_tool_file(ctx, "demo", "static_graph", str(edges_csv))
    services.import_tool_file(ctx, "demo", "designite", str(designite_csv))


def test_merges_tools_and_attaches_edges(ctx, tmp_path):
    _seed(ctx, tmp_path)
    n = services.rebuild_evidence(ctx, "demo")
    cases = ctx.store.list_cases(project_id="demo", smell_key="cyclic_dependency")
    # arcan CD_1, designite row, and the static-graph SCC all describe {a,b}
    assert len(cases) == 1
    case = ctx.store.get_case(cases[0]["id"])
    tools = {f.tool for f in case.tool_findings}
    assert {"arcan", "designite", "static_graph"} <= tools
    pairs = case.edge_pairs()
    assert ("a.pkg", "b.pkg") in pairs and ("b.pkg", "a.pkg") in pairs
    assert n == len(ctx.store.list_cases(project_id="demo"))


def test_limitation_recorded_when_no_edges(ctx, tmp_path):
    services.add_project(ctx, "noedges")
    csv = tmp_path / "s.csv"
    csv.write_text("ID,SmellType,AffectedElements\nCD_9,cyclicDep,x.pkg;y.pkg\n",
                   encoding="utf-8")
    services.import_tool_file(ctx, "noedges", "arcan", str(csv))
    services.rebuild_evidence(ctx, "noedges")
    case = ctx.store.get_case(ctx.store.list_cases(project_id="noedges")[0]["id"])
    assert any("source inspection" in l.lower() for l in case.limitations)
    assert case.dependency_evidence == []


def test_rebuild_is_idempotent(ctx, tmp_path):
    _seed(ctx, tmp_path)
    n1 = services.rebuild_evidence(ctx, "demo")
    ids1 = {c["id"] for c in ctx.store.list_cases(project_id="demo")}
    n2 = services.rebuild_evidence(ctx, "demo")
    ids2 = {c["id"] for c in ctx.store.list_cases(project_id="demo")}
    assert n1 == n2 and ids1 == ids2
