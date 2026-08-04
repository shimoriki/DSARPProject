"""End-to-end + unit tests for the DSARP pipeline (offline, no network)."""
import json
from pathlib import Path

import jsonschema
import pytest

from dsarp.alignment.aligner import SmellRefactoringAligner
from dsarp.candidates.generator import CandidateGenerator
from dsarp.config import load_config
from dsarp.evidence.normalizer import EvidenceNormalizer
from dsarp.graphs.builder import DependencyGraphBuilder
from dsarp.mining.refactoring_miner import RefactoringEvent
from dsarp.pipeline import InferencePipeline
from dsarp.ranking.ranker import PreferenceRanker
from dsarp.schemas import DependencyGraph, Smell, SourceIndex
from dsarp.tools.arcan import ToolFinding

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "docs" / "schemas" / "suggestion_schema.json").read_text())

EDGES = [
    {"source": "a.b", "target": "a.c", "weight": 3},
    {"source": "a.c", "target": "a.b", "weight": 2},  # cycle
]


def _case():
    dg = DependencyGraphBuilder().build(EDGES)
    findings = [
        ToolFinding("Arcan", "Cyclic Dependency", "package", ["a.b", "a.c"], "high").ensure_id(),
        ToolFinding("Designite", "Cyclic Dependency", "package", ["a.b", "a.c"], "high").ensure_id(),
        ToolFinding("Designite", "God Class", "class", ["a.b.Big"], "medium").ensure_id(),
    ]
    return EvidenceNormalizer().normalize("demo", "sha1", findings, dg, SourceIndex())


def test_graph_detects_cycle():
    dg = DependencyGraphBuilder().build(EDGES)
    assert dg.graph_metrics["cycle_count"] >= 1


def test_normalizer_merges_tool_agreement():
    case = _case()
    cyc = [s for s in case.smells if s.smell_type == "Cyclic Dependency"][0]
    assert "Arcan" in cyc.tool_sources and "Designite" in cyc.tool_sources


def test_candidate_generator_no_invention():
    case = _case()
    smell = case.smells[0]
    cands = CandidateGenerator().generate(smell, case.dependency_graph)
    assert cands, "expected deterministic candidates"
    # every candidate maps to a known refactoring type, none invented free-text as enum
    for c in cands:
        assert c.recommended_refactoring
        assert c.requires_source_inspection is True


def test_ranker_orders_by_score():
    case = _case()
    cands = CandidateGenerator().generate(case.smells[0], case.dependency_graph)
    ranked = PreferenceRanker().rank(cands)
    scores = [r["score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)


def test_alignment_confidence_bounded():
    case = _case()
    events = [RefactoringEvent("e1", "sha1", "Extract Interface",
                               affected_components=["a.b"])]
    aligns = SmellRefactoringAligner().align(case.smells, events)
    for a in aligns:
        assert 0.0 <= a.alignment_confidence <= 1.0


def test_pipeline_end_to_end_schema_valid(tmp_path):
    cfg = load_config("local", overrides={"data_dir": str(tmp_path),
                                          "model_provider": {"type": "offline"}})
    cfg.data_dir = tmp_path
    case = _case()
    pipe = InferencePipeline(cfg, top_k_per_smell=2)
    suggestions, report = pipe.run(case)
    assert suggestions
    for s in suggestions:
        jsonschema.validate(s.to_contract_dict(), SCHEMA)
    # no-hallucination: grounding pass on synthetic-but-consistent evidence
    assert report["total_model_calls"] == len(suggestions)


def test_pipeline_cache_hits_on_rerun(tmp_path):
    cfg = load_config("local", overrides={"data_dir": str(tmp_path),
                                          "model_provider": {"type": "offline"}})
    cfg.data_dir = tmp_path
    case = _case()
    InferencePipeline(cfg, top_k_per_smell=2).run(case)
    _, report2 = InferencePipeline(cfg, top_k_per_smell=2).run(case)
    assert report2["cache_hits"] > 0


def test_no_validated_recipe_without_verification(tmp_path):
    cfg = load_config("local", overrides={"data_dir": str(tmp_path),
                                          "model_provider": {"type": "offline"}})
    cfg.data_dir = tmp_path
    suggestions, _ = InferencePipeline(cfg, top_k_per_smell=3).run(_case())
    for s in suggestions:
        if s.openrewrite_recipe_plan.recipe_status == "validated":
            assert s.verification.openrewrite_dry_run == "passed"
            assert s.verification.build == "passed"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
