import streamlit as st
from _common import list_projects, load_suggestions, load_graph, default_index
from dsarp.schemas import DependencyGraph
from dsarp.insights import recipe_risk_meter, graph_delta_preview, issue_pr_draft

st.title("💡 Suggestions")
st.caption("Loop 10: ranked, evidence-grounded refactoring suggestions with full provenance.")

projects = list_projects()
sel = st.selectbox("Project", projects or ["(none)"],
                   index=default_index(projects or ["(none)"]))
sugs = load_suggestions(sel)
graph_data = load_graph(sel)
dg = DependencyGraph(**graph_data) if graph_data else DependencyGraph()

c = st.columns(4)
c[0].metric("Suggestions", len(sugs))
c[1].metric("Grounded", sum(1 for s in sugs if not s.get("no_hallucination_checks", {}).get("unsupported_claims")))
c[2].metric("Recipe-possible", sum(1 for s in sugs if s.get("openrewrite_recipe_plan", {}).get("recipe_possible")))
c[3].metric("Flagged", sum(1 for s in sugs if s.get("verification_status") == "flagged"))

# --- comparison view: top 3 side by side --------------------------------- #
if len(sugs) >= 2 and st.checkbox("🔀 Compare top 3 side-by-side"):
    cols = st.columns(min(3, len(sugs)))
    for col, s in zip(cols, sugs[:3]):
        with col:
            st.markdown(f"**#{s['rank']} · {s['recommended_refactoring']}**")
            st.metric("Score", f"{s['score']:.2f}")
            st.caption(f"{s['smell_type']} · risk={s.get('expected_impact', {}).get('risk_level')}")
            st.caption("Evidence: " + ", ".join(s.get("evidence_used", [])[:2]))
    st.divider()

for s in sugs:
    nh = s.get("no_hallucination_checks", {})
    flag = "✅" if not nh.get("unsupported_claims") else "⚠️"
    with st.expander(f"#{s.get('rank')} · {flag} score={s.get('score'):.2f} · "
                     f"{s.get('smell_type')} → {s.get('recommended_refactoring')}"):
        # Evidence card
        st.markdown("##### 🧾 Evidence card")
        ec = st.columns(4)
        ec[0].metric("Score", f"{s.get('score'):.2f}")
        ec[1].metric("Confidence", f"{s.get('confidence'):.2f}")
        ec[2].metric("Risk", s.get("expected_impact", {}).get("risk_level"))
        ec[3].metric("Verify", s.get("verification_status"))
        st.write("**Evidence IDs:**", s.get("evidence_used") or "requires_source_inspection")
        st.write("**Tools used:**", s.get("tools_available"), " · **Unavailable:**", s.get("tools_unavailable"))
        st.write("**Affected components:**", [a.get("id") for a in s.get("affected_components", [])])

        # No-hallucination panel (green/red)
        st.markdown("##### 🛡️ No-hallucination panel")
        checks = {
            "files_exist": nh.get("all_files_exist", True),
            "entities_exist": nh.get("all_entities_exist", True),
            "edges_supported": nh.get("all_edges_supported", True),
            "evidence_ids_ok": not any("evidence" in u for u in nh.get("unsupported_claims", [])),
            "recipe_status_honest": s.get("openrewrite_recipe_plan", {}).get("recipe_status") != "validated"
                                    or s.get("verification", {}).get("build") == "passed",
        }
        pcols = st.columns(len(checks))
        for pc, (k, v) in zip(pcols, checks.items()):
            pc.markdown(f"{'🟢' if v else '🔴'} {k}")
        if nh.get("unsupported_claims"):
            st.warning("Unsupported claims: " + "; ".join(nh["unsupported_claims"]))

        # Why this rank?
        st.markdown("##### 📊 Why this rank?")
        rb = s.get("rank_breakdown", {})
        st.bar_chart({k: v for k, v in rb.items() if isinstance(v, (int, float)) and v >= 0})
        st.caption(f"final={rb.get('final')} · graph={rb.get('graph_score')} · "
                   f"ranker={rb.get('ranker_score')} · evidence_conf={rb.get('evidence_confidence')} · "
                   f"risk={rb.get('risk')}")

        # Recipe risk + graph delta
        st.markdown("##### 🎚️ Recipe risk & graph delta")
        rr = recipe_risk_meter(s)
        gd = graph_delta_preview(s, dg)
        rc = st.columns(2)
        rc[0].metric("Recipe risk", f"{rr['risk_meter']} ({rr['band']})")
        rc[1].metric("Cycles before→after", f"{gd['cycles_before']} → {gd['estimated_cycles_after']}")

        # Reasoning + plan
        st.markdown("##### 🧠 Reasoning")
        st.write(s.get("reasoning"))
        st.write("**Implementation plan:**")
        for step in s.get("implementation_plan", []):
            st.write("-", step)
        st.write("**Target boundary:**", s.get("target_boundary"))

        # Recipe status
        plan = s.get("openrewrite_recipe_plan", {})
        st.write(f"**OpenRewrite:** `{plan.get('recipe_status')}` · {plan.get('recipe_type')}")

        # Issue/PR draft
        if st.button("📝 Generate issue/PR draft (no push)", key=f"draft_{s['suggestion_id']}"):
            st.code(issue_pr_draft(s), language="markdown")
        st.caption("Limitations: " + ", ".join(s.get("limitations", []) or ["none"]))
