"""The validated path must meet the contract the project declares for every suggestion.

docs/schemas/suggestion_schema.json is checked here directly, not paraphrased: the pipeline
that emitted schema-valid suggestions was the one whose verdicts came from a regex index over
imports, and the pipeline with bytecode-verified results emitted patches and nothing else.
"""
import json
from pathlib import Path

import jsonschema
import pytest

from dsarp.experiments.suggestions import from_row

SCHEMA = json.loads((Path(__file__).resolve().parents[1]
                     / "docs/schemas/suggestion_schema.json").read_text(encoding="utf-8"))

ACCEPTED = {
    "edge": "org.apache.pdfbox -> org.apache.pdfbox.pdmodel",
    "type": "org.apache.pdfbox.Loader", "to_package": "org.apache.pdfbox.pdmodel",
    "predicted_removed": 18, "predicted_added": 2, "predicted_net": -16,
    "success_criterion": "the bytecode edge x -> y no longer exists",
    "applied": True, "compile": "compiled", "jdeps_agrees": True,
    "before_apply": {"ok": True, "public_api": True, "why": None},
    "after_apply": {"ok": True},
    "structural": {"ok": True, "edge_removed": True, "edges_removed": 18, "edges_added": ["a -> b", "c -> d"],
                   "cycles_before": 5, "cycles_after": 5},
    "behavioural": {"ok": True},
    "tests": {"status": "passed", "tests_run": 2050, "failures": 0, "errors": 0},
    "verdict": {"accepted": True, "failed_gate": None, "why": None},
}

REJECTED = {
    "edge": "org.apache.pdfbox.debugger -> org.apache.pdfbox.debugger.ui",
    "type": "org.apache.pdfbox.debugger.PDFDebugger",
    "to_package": "org.apache.pdfbox.debugger.ui",
    "predicted_removed": 26, "predicted_added": 15, "predicted_net": -11,
    "success_criterion": "the bytecode edge x -> y no longer exists",
    "applied": True,
    "before_apply": {"ok": False, "public_api": True,
                     "why": "1 files name this class as text; a move does not rewrite them"},
    "after_apply": {"ok": False, "why": "1 files still name ...PDFDebugger after the move"},
    "verdict": {"accepted": False, "failed_gate": "after_apply",
                "why": "1 files still name ...PDFDebugger after the move"},
}


@pytest.mark.parametrize("row", [ACCEPTED, REJECTED])
def test_the_emitted_suggestion_validates_against_the_declared_schema(row, tmp_path):
    jsonschema.validate(from_row(row, tmp_path, "apache-pdfbox"), SCHEMA)


def test_gates_that_never_ran_are_not_reported_as_passed():
    s = from_row(REJECTED, Path("."), "apache-pdfbox")
    # the build never completed, so tests and graph re-analysis cannot have passed
    assert s["verification"]["tests"] == "not_run"
    assert s["verification"]["graph_reanalysis"] == "not_run"
    assert s["verification"]["build"] == "failed"
    assert s["verification_status"] == "rejected"


def test_confidence_is_verification_not_a_guess():
    assert from_row(ACCEPTED, Path("."), "p")["confidence"] == 1.0
    assert from_row(REJECTED, Path("."), "p")["confidence"] == 0.0


def test_an_unchanged_cycle_count_is_stated_as_a_limitation():
    s = from_row(ACCEPTED, Path("."), "p")
    assert any("no cycle was dissolved" in l for l in s["limitations"])
    assert s["expected_impact"]["cycle_reduction"] == 0.0
    # 18 edges out, 2 in
    assert s["expected_impact"]["coupling_reduction_estimate"] == 16.0
    assert s["expected_impact"]["smell_removed"] == "partial"


def test_moving_a_public_type_is_declared_a_limitation():
    s = from_row(ACCEPTED, Path("."), "p")
    assert any("downstream build" in l for l in s["limitations"])


def test_a_rejection_names_the_gate_that_refused_it():
    s = from_row(REJECTED, Path("."), "p")
    assert any("rejected at the after_apply gate" in l for l in s["limitations"])
    assert s["expected_impact"]["risk_level"] == "high"


def test_a_disagreement_between_readers_is_an_unsupported_claim():
    s = from_row(dict(ACCEPTED, jdeps_agrees=False), Path("."), "p")
    assert s["no_hallucination_checks"]["unsupported_claims"]
