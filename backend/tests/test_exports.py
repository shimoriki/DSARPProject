import json
from pathlib import Path

from dsarp import services


def _reviewed_runs(ctx, tmp_path):
    services.add_project(ctx, "demo")
    csv = tmp_path / "smells.csv"
    csv.write_text("ID,SmellType,AffectedElements\n"
                   "CD_1,cyclicDep,a.x;a.y\nCD_2,cyclicDep,b.x;b.y\n",
                   encoding="utf-8")
    services.import_tool_file(ctx, "demo", "arcan", str(csv))
    services.rebuild_evidence(ctx, "demo")
    runs = services.run_agents(ctx, "demo", "tool_evidence",
                               provider_name="mock", model_id="mock")
    high = {"evidence_grounding": 5, "refactoring_relevance": 5,
            "architectural_reasoning": 4, "minimality_and_safety": 4,
            "actionability": 5, "human_confidence": 4, "cost_efficiency": 4}
    low = {c: 2 for c in high}
    services.save_review(ctx, runs[0]["run_id"], high, "yes", "accept", "good",
                         edited_output_json='{"note": "human edited"}')
    services.save_review(ctx, runs[1]["run_id"], low, "no", "reject", "bad")
    return runs


def test_export_filters_by_hgrs_and_prefers_edited_output(ctx, tmp_path):
    _reviewed_runs(ctx, tmp_path)
    result = services.export_dataset(ctx, min_hgrs=4.0, lora_prep=True)
    assert result["examples"] == 1  # only the high-HGRS review passes
    inst = Path(result["files"]["instruction"])
    lines = [json.loads(l) for l in inst.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 1
    assert lines[0]["output"] == '{"note": "human edited"}'
    assert lines[0]["meta"]["hgrs"] >= 4.0
    chat = Path(result["files"]["chat"])
    msg = json.loads(chat.read_text(encoding="utf-8").splitlines()[0])
    assert [m["role"] for m in msg["messages"]] == ["system", "user", "assistant"]
    assert Path(result["files"]["csv"]).exists()
    assert Path(result["lora_prep_dir"]).joinpath("README.md").exists()


def test_comparison_table_groups_modes(ctx, tmp_path):
    _reviewed_runs(ctx, tmp_path)
    services.run_agents(ctx, "demo", "baseline",
                        provider_name="mock", model_id="mock")
    table = services.comparison_table(ctx, "demo")
    modes = {row["agent_mode"] for row in table}
    assert {"baseline", "tool_evidence"} <= modes
    te = next(r for r in table if r["agent_mode"] == "tool_evidence")
    assert te["json_validity_rate"] == 1.0
    assert te["mean_hgrs"] is not None
