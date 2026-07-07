import json

from dsarp import services
from dsarp.agents.runner import extract_json, run_suggestion
from dsarp.models.suggestion import AgentMode
from dsarp.providers.base import ChatResult


def _prepare_case(ctx, tmp_path):
    services.add_project(ctx, "demo")
    smells = tmp_path / "smells.csv"
    smells.write_text("ID,SmellType,AffectedElements,Severity\n"
                      "CD_1,cyclicDep,a.pkg;b.pkg,high\n", encoding="utf-8")
    edges = tmp_path / "edges.csv"
    edges.write_text("from,to\na.pkg,b.pkg\nb.pkg,a.pkg\n", encoding="utf-8")
    services.import_tool_file(ctx, "demo", "arcan", str(smells))
    services.import_tool_file(ctx, "demo", "static_graph", str(edges))
    services.rebuild_evidence(ctx, "demo")
    case_row = ctx.store.list_cases(project_id="demo",
                                    smell_key="cyclic_dependency")[0]
    return ctx.store.get_case(case_row["id"])


def test_extract_json_from_noisy_text():
    text = 'Sure! Here you go:\n```json\n{"a": {"b": "c}"}}\n``` extra'
    assert json.loads(extract_json(text)) == {"a": {"b": "c}"}}


def test_mock_run_produces_valid_grounded_suggestion(ctx, tmp_path):
    case = _prepare_case(ctx, tmp_path)
    provider = ctx.provider("mock", "mock")
    run = run_suggestion(ctx.cfg, ctx.store, provider, case,
                         AgentMode.tool_evidence,
                         skill_name="BreakCyclicDependencySkill",
                         skill_version="v0", skill_text="skill body")
    assert run["status"] == "ok"
    suggestion = json.loads(run["suggestion_json"])
    assert suggestion["run_id"] == run["run_id"]
    assert suggestion["agent_mode"] == "tool_evidence"
    checks = json.loads(run["structural_checks_json"])
    assert checks["critical_hallucination"] is False
    assert run["total_tokens"] > 0
    scores = ctx.store.get_suggested_scores(run["run_id"])
    assert "deterministic" in scores
    assert set(scores["deterministic"]) == {
        "evidence_grounding", "refactoring_relevance", "architectural_reasoning",
        "minimality_and_safety", "actionability", "human_confidence",
        "cost_efficiency"}
    # critical scoring: automation never pre-fills human confidence above floor
    assert scores["deterministic"]["human_confidence"]["score"] == 1
    # grounded run earns its evidence score through verified checks
    assert scores["deterministic"]["evidence_grounding"]["score"] >= 4


class _BrokenProvider:
    name = "broken"
    model_id = "broken"

    def __init__(self):
        self.calls = 0

    def chat(self, system, user, **kwargs):
        self.calls += 1
        return ChatResult(text="this is not json at all", prompt_tokens=1,
                          completion_tokens=1, total_tokens=2, runtime_seconds=0.0)


def test_invalid_json_gets_one_repair_then_stored_malformed(ctx, tmp_path):
    case = _prepare_case(ctx, tmp_path)
    provider = _BrokenProvider()
    run = run_suggestion(ctx.cfg, ctx.store, provider, case, AgentMode.baseline)
    assert provider.calls == 2  # exactly one repair attempt
    assert run["status"] == "invalid_json"
    assert run["repair_attempted"] == 1
    malformed = ctx.store.list_malformed(run["run_id"])
    assert len(malformed) == 1
    assert "not json" in malformed[0]["raw_text"]


class _HallucinatingProvider:
    name = "hallucinator"
    model_id = "hallucinator"

    def chat(self, system, user, **kwargs):
        payload = {
            "evidence_used": ["TOTALLY_FAKE_ID"],
            "observed_tool_evidence": ["made up fact"],
            "candidate_boundary_to_inspect": {
                "components": ["a.pkg", "b.pkg"],
                "edge_direction_status": "supported_by_evidence",
                "reason": "trust me"},
            "recommended_refactoring": "Move Class",
            "rationale": "because",
            "implementation_steps": ["do it"],
            "affected_components": ["not.a.real.pkg"],
            "risks_and_tradeoffs": [],
            "assumptions_and_questions": [],
            "expected_benefit": "",
            "confidence": 0.9,
            "limitations": ""}
        return ChatResult(text=json.dumps(payload), prompt_tokens=1,
                          completion_tokens=1, total_tokens=2)


def test_hallucination_flagged_and_grounding_penalized(ctx, tmp_path):
    case = _prepare_case(ctx, tmp_path)
    run = run_suggestion(ctx.cfg, ctx.store, _HallucinatingProvider(), case,
                         AgentMode.tool_evidence)
    assert run["status"] == "ok"  # valid JSON, but flagged
    checks = json.loads(run["structural_checks_json"])
    assert checks["critical_hallucination"] is True
    assert "TOTALLY_FAKE_ID" in checks["unsupported_evidence_ids"]
    # any fabricated claim floors evidence grounding to 1
    assert checks["suggested_scores"]["evidence_grounding"]["score"] == 1
