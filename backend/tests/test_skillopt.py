import json

from dsarp import services
from dsarp.skillopt.digest import build_digest
from dsarp.skillopt.optimizer import next_version


def _full_loop_setup(ctx, tmp_path):
    services.add_project(ctx, "demo")
    lines = ["ID,SmellType,AffectedElements"]
    for i in range(6):
        lines.append(f"CD_{i},cyclicDep,q{i}.a;q{i}.b")
    csv = tmp_path / "smells.csv"
    csv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    services.import_tool_file(ctx, "demo", "arcan", str(csv))
    services.rebuild_evidence(ctx, "demo")
    services.split_evidence(ctx, "demo")
    runs = services.run_agents(ctx, "demo", "tool_evidence",
                               provider_name="mock", model_id="mock",
                               split="train")
    for run in runs:
        suggested = ctx.store.get_suggested_scores(run["run_id"])["deterministic"]
        scores = {c: v["score"] for c, v in suggested.items()}
        services.save_review(ctx, run["run_id"], scores, "maybe", "revise",
                             "steps too vague; missing risk discussion")
    return runs


def test_digest_aggregates_reviews(ctx, tmp_path):
    _full_loop_setup(ctx, tmp_path)
    digest = build_digest(ctx.store, "BreakCyclicDependencySkill", "v0")
    assert digest["reviews_aggregated"] >= 1
    assert 1.0 <= digest["mean_hgrs"] <= 5.0
    assert set(digest["mean_by_criterion"]) == {
        "evidence_grounding", "refactoring_relevance", "architectural_reasoning",
        "minimality_and_safety", "actionability", "human_confidence",
        "cost_efficiency"}
    assert digest["unsupported_evidence_claim_rate"] == 0.0


def test_optimizer_writes_candidate_without_touching_v0(ctx, tmp_path):
    _full_loop_setup(ctx, tmp_path)
    v0_path = ctx.cfg.skills_path / "BreakCyclicDependencySkill_v0.md"
    v0_before = v0_path.read_text(encoding="utf-8")
    result = services.optimize(ctx, "BreakCyclicDependencySkill", "v0",
                               provider_name="mock", model_id="mock")
    assert result["candidate_version"] == "v1_candidate"
    candidate = ctx.cfg.resolve(result["file_path"])
    assert candidate.exists()
    assert v0_path.read_text(encoding="utf-8") == v0_before  # never overwritten
    row = ctx.store.get_skill("BreakCyclicDependencySkill", "v1_candidate")
    assert row["status"] == "candidate"


def test_validation_and_gated_promotion(ctx, tmp_path):
    _full_loop_setup(ctx, tmp_path)
    services.optimize(ctx, "BreakCyclicDependencySkill", "v0",
                      provider_name="mock", model_id="mock")
    report = services.validate(ctx, "demo", "BreakCyclicDependencySkill",
                               "v0", "v1_candidate",
                               provider_name="mock", model_id="mock")
    assert "hgrs_improvement" in report
    assert report["baseline"]["n_scored"] >= 1
    # mock provider gives identical output for both versions -> gate fails
    assert report["passed"] is False
    assert any("HGRS improvement" in r for r in report["fail_reasons"])
    # promotion must refuse a failed gate
    try:
        services.approve_and_promote(ctx, report["report_id"])
        raised = False
    except ValueError:
        raised = True
    assert raised
    prod = ctx.store.production_skill("BreakCyclicDependencySkill")
    assert prod["version"] == "v0"  # unchanged


def test_promotion_gate_logic_passes_when_criteria_met(ctx, tmp_path):
    """Force a passing report through the store to test the promotion path."""
    _full_loop_setup(ctx, tmp_path)
    services.optimize(ctx, "BreakCyclicDependencySkill", "v0",
                      provider_name="mock", model_id="mock")
    report = {"baseline": {"mean_hgrs": 3.0, "mean_grounding": 4.0},
              "candidate": {"mean_hgrs": 3.5, "mean_grounding": 4.2,
                            "critical_hallucinations": 0},
              "hgrs_improvement": 0.5, "grounding_delta": 0.2}
    report_id = ctx.store.save_validation_report(
        "BreakCyclicDependencySkill", "v0", "v1_candidate", report, passed=True)
    result = services.approve_and_promote(ctx, report_id, approver="tester")
    assert result["production_version"] == "v1"
    prod = ctx.store.production_skill("BreakCyclicDependencySkill")
    assert prod["version"] == "v1"
    stored = ctx.store.get_validation_report(report_id)
    assert stored["human_approved"] == 1 and stored["promoted"] == 1


def test_next_version():
    assert next_version("v0") == "v1"
    assert next_version("v7") == "v8"
