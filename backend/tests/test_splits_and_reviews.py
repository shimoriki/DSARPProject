from dsarp import services


def _seed_cases(ctx, tmp_path, project="demo", n=8):
    services.add_project(ctx, project)
    lines = ["ID,SmellType,AffectedElements"]
    for i in range(n):
        lines.append(f"CD_{i},cyclicDep,p{i}.a;p{i}.b")
    csv = tmp_path / f"{project}.csv"
    csv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    services.import_tool_file(ctx, project, "arcan", str(csv))
    services.rebuild_evidence(ctx, project)


def test_split_no_overlap_and_deterministic(ctx, tmp_path):
    _seed_cases(ctx, tmp_path)
    counts1 = services.split_evidence(ctx, "demo")
    assignment1 = {c["id"]: c["split"] for c in ctx.store.list_cases(project_id="demo")}
    counts2 = services.split_evidence(ctx, "demo")
    assignment2 = {c["id"]: c["split"] for c in ctx.store.list_cases(project_id="demo")}
    assert assignment1 == assignment2
    assert counts1 == counts2
    assert all(s in ("train", "validation") for s in assignment1.values())
    assert counts1["validation"] >= 1 and counts1["train"] >= 1


def test_project_level_split_holds_out_whole_projects(ctx, tmp_path):
    _seed_cases(ctx, tmp_path, "alpha", 3)
    _seed_cases(ctx, tmp_path, "beta", 3)
    _seed_cases(ctx, tmp_path, "gamma", 3)
    services.split_evidence(ctx, None)
    for project in ("alpha", "beta", "gamma"):
        splits = {c["split"] for c in ctx.store.list_cases(project_id=project)}
        assert len(splits) == 1  # a whole project is either train or validation


def test_review_saves_computed_hgrs_and_audit(ctx, tmp_path):
    _seed_cases(ctx, tmp_path, "demo", 1)
    runs = services.run_agents(ctx, "demo", "tool_evidence",
                               provider_name="mock", model_id="mock")
    run = runs[0]
    scores = {"evidence_grounding": 5, "refactoring_relevance": 4,
              "architectural_reasoning": 4, "minimality_and_safety": 3,
              "actionability": 4, "human_confidence": 3, "cost_efficiency": 5}
    review = services.save_review(ctx, run["run_id"], scores, "yes", "accept",
                                  "solid suggestion")
    expected = (0.25 * 5 + 0.20 * 4 + 0.15 * 4 + 0.15 * 3
                + 0.10 * 4 + 0.10 * 3 + 0.05 * 5)
    assert review.hgrs == round(expected, 3)
    stored = ctx.store.review_for_run(run["run_id"])
    assert stored["hgrs"] == review.hgrs
    assert any(a["entity_type"] == "review" for a in ctx.store.list_audit())
