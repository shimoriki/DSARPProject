import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _bootstrap import (SUGGESTED_LABEL, evidence_backed_banner, get_ctx,  # noqa: E402
                        project_selector)
from dsarp import services  # noqa: E402
from dsarp.hgrs import CRITERIA, CRITERION_LABELS, compute_hgrs  # noqa: E402

st.set_page_config(page_title="Human Review", layout="wide")
ctx = get_ctx()
st.title("5 · Human Review (HGRS)")
st.caption("All suggested values are machine-generated hints. "
           "You can overwrite every score, comment, and decision.")

pname = project_selector(ctx)
if pname:
    runs = [r for r in ctx.store.list_runs(project_id=pname) if r["status"] == "ok"]
    if not runs:
        st.info("No successful agent runs to review yet.")
        st.stop()

    reviewed_ids = {rv["run_id"] for rv in ctx.store.list_reviews(project_id=pname)}
    unreviewed_first = sorted(
        runs, key=lambda r: (r["run_id"] in reviewed_ids, r["created_at"]))
    labels = {r["run_id"]: (f"{r['smell_id']} · {r['agent_mode']} · {r['model_id']} · "
                            f"{'REVIEWED' if r['run_id'] in reviewed_ids else 'unreviewed'}")
              for r in unreviewed_first}
    run_id = st.selectbox("Run to review", [r["run_id"] for r in unreviewed_first],
                          format_func=labels.get)
    run = ctx.store.get_run(run_id)
    case = ctx.store.get_case(run["case_id"])
    suggestion = json.loads(run["suggestion_json"])
    checks = json.loads(run.get("structural_checks_json") or "{}")
    suggested_sets = ctx.store.get_suggested_scores(run_id)

    evidence_backed_banner(checks)

    left, right = st.columns(2)
    with left:
        st.subheader("Normalized evidence (raw)")
        if case.limitations:
            st.warning("Limitations:\n\n- " + "\n- ".join(case.limitations))
        st.json(case.public_dict())
        st.subheader("Tool provenance")
        for f in case.tool_findings:
            st.text(f"• {f.evidence_id}  tool={f.tool}  record={f.tool_record_id}  "
                    f"file={f.raw_source_file}")

    with right:
        st.subheader("Suggested refactoring")
        st.markdown(f"**{suggestion['recommended_refactoring']}** — "
                    f"confidence {suggestion['confidence']}")
        st.markdown(suggestion["rationale"])
        st.markdown("**Implementation steps**")
        for i, step in enumerate(suggestion["implementation_steps"], 1):
            st.markdown(f"{i}. {step}")
        st.markdown("**Evidence IDs used by the model**")
        st.code(", ".join(suggestion["evidence_used"]) or "(none)")
        st.markdown("**Candidate boundary to inspect**")
        st.json(suggestion["candidate_boundary_to_inspect"])
        with st.expander("Full suggestion JSON"):
            st.json(suggestion)
        st.subheader("Automatic structural checks")
        for c in checks.get("checks", []):
            icon = "✅" if c["passed"] else "❌"
            st.text(f"{icon} {c['name']}: {c['detail']}")
        st.subheader("Agent / model / skill metadata")
        st.code(f"agent_mode      = {run['agent_mode']}\n"
                f"provider        = {run['provider']}\n"
                f"model_id        = {run['model_id']}\n"
                f"skill_version   = {run['skill_version']}\n"
                f"prompt_version  = {run['prompt_version']}\n"
                f"evidence_ver    = {run['evidence_version']}\n"
                f"tokens          = {run['total_tokens']} "
                f"(prompt {run['prompt_tokens']} / completion {run['completion_tokens']})\n"
                f"runtime_seconds = {run['runtime_seconds']}\n"
                f"repair_attempted= {run['repair_attempted']}", language="ini")

    st.divider()
    st.subheader("HGRS scoring")

    source = "deterministic"
    if "critic" in suggested_sets:
        source = st.radio("Pre-fill scores from",
                          ["deterministic", "critic"], horizontal=True)
    prefill = suggested_sets.get(source, {})
    existing = ctx.store.review_for_run(run_id)

    with st.form("review_form"):
        scores: dict[str, int] = {}
        cols = st.columns(4)
        for i, criterion in enumerate(CRITERIA):
            entry = prefill.get(criterion, {})
            default = int(existing[criterion]) if existing else int(entry.get("score", 3))
            with cols[i % 4]:
                scores[criterion] = st.slider(
                    CRITERION_LABELS[criterion], 1, 5, default, key=f"s_{criterion}")
                if entry:
                    st.caption(f"🔎 {SUGGESTED_LABEL}: **{entry.get('score')}** "
                               f"({source}) — {entry.get('reason', '')[:160]}")
        would_try = st.radio("Would you try this refactoring?",
                             ["yes", "maybe", "no"], horizontal=True,
                             index=["yes", "maybe", "no"].index(
                                 existing["would_try_it"]) if existing else 1)
        decision = st.radio("Final recommendation decision",
                            ["accept", "revise", "reject"], horizontal=True,
                            index=["accept", "revise", "reject"].index(
                                existing["decision"]) if existing else 1)
        notes = st.text_area("Reviewer comments",
                             value=existing["reviewer_notes"] if existing else "")
        edited = st.text_area(
            "Human-edited preferred output (JSON, optional — used for dataset export)",
            value=(existing["edited_output_json"] if existing and
                   existing["edited_output_json"] else ""),
            height=200, placeholder="Leave empty to keep the agent output as-is")
        submitted = st.form_submit_button("Save review")

    live_hgrs = compute_hgrs(scores, ctx.cfg.hgrs_weights)
    st.metric("HGRS (weighted)", live_hgrs)

    if submitted:
        if edited.strip():
            try:
                json.loads(edited)
            except json.JSONDecodeError as exc:
                st.error(f"Edited output is not valid JSON: {exc}")
                st.stop()
        review = services.save_review(
            ctx, run_id, scores, would_try, decision, notes,
            edited.strip() or None)
        st.success(f"Review saved. HGRS = {review.hgrs} "
                   f"(reviewer: {review.reviewer_id})")
