from pathlib import Path

from dsarp.adapters import get_adapter
from dsarp.registry import canonical_smell


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_arcan_smell_csv(tmp_path):
    p = _write(tmp_path, "ArchitectureSmells.csv",
               "ID,SmellType,AffectedElements,Severity,Size,ATDI\n"
               "CD_1,cyclicDep,a.pkg;b.pkg,high,2,0.7\n"
               "HL_1,hubLikeDep,hub.pkg,medium,,0.4\n")
    result = get_adapter("arcan").parse_import(p)
    assert len(result.smells) == 2
    cd = result.smells[0]
    assert cd.affected_components == ["a.pkg", "b.pkg"]
    assert cd.attributes["severity"] == "high"
    key, display, code = canonical_smell(cd.smell_type_raw)
    assert key == "cyclic_dependency" and code == "CD"


def test_arcan_edge_csv(tmp_path):
    p = _write(tmp_path, "DependencyEdges.csv",
               "Source,Target,Weight\na.pkg,b.pkg,4\nb.pkg,a.pkg,2\n")
    result = get_adapter("arcan").parse_import(p)
    assert not result.smells
    assert len(result.edges) == 2
    assert result.edges[0].from_component == "a.pkg"
    assert result.edges[0].weight == 4.0


def test_designite_cycle_participants(tmp_path):
    p = _write(tmp_path, "ArchitectureSmells.csv",
               'Project Name,Package Name,Architecture Smell,Cause of the Smell\n'
               'demo,a.pkg,Cyclic Dependency,"Participates in a dependency cycle '
               'with: b.pkg, c.pkg"\n')
    result = get_adapter("designite").parse_import(p)
    assert len(result.smells) == 1
    assert set(result.smells[0].affected_components) == {"a.pkg", "b.pkg", "c.pkg"}


def test_static_graph_detects_scc(tmp_path):
    p = _write(tmp_path, "edges.csv",
               "from,to\na,b\nb,c\nc,a\nc,d\n")
    result = get_adapter("static_graph").parse_import(p)
    assert len(result.edges) == 4
    cycles = [s for s in result.smells if s.smell_type_raw == "Cyclic Dependency"]
    assert len(cycles) == 1
    assert sorted(cycles[0].affected_components) == ["a", "b", "c"]


def test_static_graph_json_adjacency(tmp_path):
    p = _write(tmp_path, "graph.json", '{"x": ["y"], "y": ["x"]}')
    result = get_adapter("static_graph").parse_import(p)
    assert len(result.edges) == 2
    assert len(result.smells) == 1


def test_unknown_smell_maps_to_custom():
    key, display, code = canonical_smell("Weird Proprietary Smell")
    assert key == "custom_tool_smell"
    assert code == "XX"


def test_arcan_bracketed_elements_and_real_columns(tmp_path):
    p = _write(tmp_path, "smell-characteristics.csv",
               "project,versionId,ATDI,AffectedElements,Severity,Size,smellType,vertexId\n"
               'tika,abc,42.5,"[org.a, org.b, org.c]",4,3,cyclicDep,101009\n')
    result = get_adapter("arcan").parse_import(p)
    assert len(result.smells) == 1
    s = result.smells[0]
    assert s.affected_components == ["org.a", "org.b", "org.c"]
    assert s.tool_record_id == "101009"
    assert canonical_smell(s.smell_type_raw)[0] == "cyclic_dependency"


def test_arcan_component_metrics_file(tmp_path):
    p = _write(tmp_path, "component-metrics.csv",
               "project,FanIn,FanOut,InstabilityMetric,LinesOfCode,name,vertexLabel\n"
               "tika,1,18,0.96,490,org.a.cli,container\n")
    result = get_adapter("arcan").parse_import(p)
    assert not result.smells and not result.edges
    metrics = {(m.component, m.name): m.value for m in result.metrics}
    assert metrics[("org.a.cli", "FanIn")] == "1"
    assert metrics[("org.a.cli", "LinesOfCode")] == "490"


def test_designite_real_cycle_description(tmp_path):
    p = _write(tmp_path, "ArchitectureSmells.csv",
               "Project,Package,Smell,Description\n"
               'tika,org.a,Cyclic Dependency,"The tool detected the smell in this '
               'component because this component participates in a cyclic dependency. '
               'The participating components in the cycle are: org.a; org.b; org.a"\n'
               'tika,org.c,God Component,"high number of classes. Number of classes '
               'in the component are: 54"\n')
    result = get_adapter("designite").parse_import(p)
    cyc = next(s for s in result.smells if "Cyclic" in s.smell_type_raw)
    assert set(cyc.affected_components) == {"org.a", "org.b"}
    god = next(s for s in result.smells if "God" in s.smell_type_raw)
    assert god.affected_components == ["org.c"]  # "54" must not leak in


def test_designite_class_level_component(tmp_path):
    p = _write(tmp_path, "DesignSmells.csv",
               "Project,Package,Class,Smell,Description,File\n"
               "tika,org.a,Foo,Feature Envy,likes members of Bar,/x/Foo.java\n")
    result = get_adapter("designite").parse_import(p)
    assert result.smells[0].affected_components == ["org.a.Foo"]
