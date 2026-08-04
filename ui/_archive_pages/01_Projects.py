import streamlit as st
from _common import list_projects, load_case, load_graph, load_report

st.title("📦 Projects")
projects = list_projects()
if not projects:
    st.info("No projects yet — stage sample data or run the mining pipeline.")
for p in projects:
    case = load_case(p) or {}
    g = load_graph(p).get("graph_metrics", {})
    rep = load_report(p)
    st.subheader(p)
    c = st.columns(6)
    c[0].metric("Revision", (case.get("revision") or "—")[:10])
    c[1].metric("Smells", len(case.get("smells", [])))
    c[2].metric("Graph nodes", g.get("node_count", 0))
    c[3].metric("Cycles", g.get("cycle_count", 0))
    c[4].metric("Suggestions", rep.get("num_suggestions", 0))
    c[5].metric("Grounding", rep.get("evidence_grounding_pass_rate", "—"))
    st.divider()
