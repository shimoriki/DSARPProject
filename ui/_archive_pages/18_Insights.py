import streamlit as st
from _common import cfg, list_projects, load_suggestions, load_case
from dsarp.schemas import EvidenceCase
from dsarp.util import read_json
from dsarp import insights as I

st.title("🔭 Insights")
st.caption("Whole-system analysis — all evidence-grounded, no fabricated data.")

projects = list_projects()
sel = st.selectbox("Project", projects or ["(none)"])
case_data = load_case(sel)
case = EvidenceCase(**case_data) if case_data else None
sugs = load_suggestions(sel)

tabs = st.tabs(["Health Radar", "Evidence Conflicts", "Pattern Library",
                "Active Learning", "Readiness", "No-Halluc. Leaderboard"])

with tabs[0]:
    if case:
        radar = I.architecture_health_radar(case)
        cc = st.columns(4)
        cc[0].metric("Cycles", radar["cycles"])
        cc[1].metric("Smells", radar["smell_count"])
        cc[2].metric("Avg instability", radar["avg_instability"])
        cc[3].metric("Max coupling", radar["max_coupling"])
        st.bar_chart(radar["radar"])
        st.caption(f"Unstable components: {radar['unstable_components']}")

with tabs[1]:
    if case:
        conflicts = I.evidence_conflict_detector(case)
        st.metric("Conflicts", len(conflicts))
        st.json(conflicts)

with tabs[2]:
    aligns = read_json(cfg().data_dir / "aligned_examples" / f"{sel}.json", default=[]) or []
    st.json(I.refactoring_pattern_library(aligns))

with tabs[3]:
    q = I.active_learning_queue(sugs)
    st.caption("Suggestions where graph score and ranker score disagree most — review first.")
    st.json(q or {"note": "no disagreement (or no learned ranker score)"})

with tabs[4]:
    st.json(I.repository_readiness_score(sugs))

with tabs[5]:
    st.caption("Compare providers by grounding + validity (needs multiple provider runs).")
    st.json(I.no_hallucination_leaderboard([{"provider": "current", "suggestions": sugs}]))
