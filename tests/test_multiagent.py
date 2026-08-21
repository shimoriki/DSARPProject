"""Severity ranking and the transformer adapter — the only new logic worth a check."""
from dsarp.multiagent import rank_by_severity, severity_of


def test_severity_reads_numbers_words_and_prose():
    assert severity_of({"severity": 4.27}) == 4.27
    assert severity_of({"severity": "3.31"}) == 3.31
    assert severity_of({"severity": "critical"}) == 4.0
    assert severity_of({"description": "... Severity: 3.3071. Size: 3."}) == 3.3071
    assert severity_of({}) == 2.0                      # unknown -> medium, never 0


def test_rank_is_worst_first_and_stable():
    a = {"id": "a", "severity": "low"}
    b = {"id": "b", "severity": 4.27}
    c = {"id": "c", "severity": "high"}
    d = {"id": "d", "severity": "high"}               # ties keep detector order
    assert [f["id"] for f in rank_by_severity([a, b, c, d])] == ["b", "c", "d", "a"]


def test_transformer_predictions_parse(tmp_path):
    from dsarp.multiagent import refactor_transformer_agent
    csv = tmp_path / "p.csv"
    csv.write_text(
        "project,versionId,architecture_smell,affected_elements,input_text,suggestions\n"
        'logging-log4j2,abc,Cyclic Dependency,a.b|a.c,"Severity: 4.26. Size: 4.",'
        '"Move Class (0.484) | Extract Method (0.47)"\n', encoding="utf-8")
    bb = refactor_transformer_agent(
        {"project_id": "apache-logging-log4j2", "predictions_csv": csv, "cfg": None})
    p = bb["transformer_plans"][0]
    assert p["refactoring"] == "Move Class" and p["confidence"] == 0.484
    assert p["severity"] == 4.26 and p["executable"] is False


class _P:
    """Minimal stand-in for a Plan — consensus only reads three attributes."""
    def __init__(self, smell, comps, applicable=True):
        self.smell_type, self.components, self.applicable = smell, comps, applicable


def test_consensus_matches_on_smell_and_component_not_refactoring_name():
    """658 of 716 log4j2 predictions are 'Move And Rename Method' while the rule agent
    relocates packages, so name-matching would agree never. Agreement is on WHAT to fix."""
    from dsarp.multiagent import consensus
    rules = [_P("Cyclic Dependency", ["org.apache.log4j.bridge"]),
             _P("God Component", ["org.apache.log4j.spi"]),
             _P("Cyclic Dependency", ["not.flagged"], applicable=False)]   # skipped
    preds = [{"smell_type": "Cyclic Dependency", "components": ["org.apache.log4j.bridge"],
              "refactoring": "Move And Rename Method"}]
    r = consensus(rules, preds)
    assert len(r["agreed"]) == 1 and len(r["rule_only"]) == 1        # inapplicable excluded
    assert r["agreed"][0][0].components == ["org.apache.log4j.bridge"]
    assert r["agreed"][0][1]["refactoring"] == "Move And Rename Method"


def test_consensus_is_empty_when_nothing_overlaps():
    from dsarp.multiagent import consensus
    r = consensus([_P("Cyclic Dependency", ["a.b"])],
                  [{"smell_type": "Cyclic Dependency", "components": ["x.y"]}])
    assert r["agreed"] == [] and len(r["rule_only"]) == 1


def test_consensus_sees_through_move_descriptions():
    """Plans record a component as the move ("a.b -> a"); the transformer reports bare names.
    Raw string comparison reported 0 agreed of 307 on log4j2 while both named the same package."""
    from dsarp.multiagent import consensus
    rules = [_P("Cyclic Dependency", ["org.apache.log4j.bridge -> org.apache.log4j"])]
    preds = [{"smell_type": "Cyclic Dependency", "components": ["org.apache.log4j.bridge"],
              "refactoring": "Move And Rename Method"}]
    assert len(consensus(rules, preds)["agreed"]) == 1
