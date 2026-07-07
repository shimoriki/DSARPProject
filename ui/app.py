"""DSARP Refactoring Suggestion Studio — local console home page.

Run with:  streamlit run ui/app.py
"""
import streamlit as st

from _bootstrap import get_ctx
from dsarp import services

st.set_page_config(page_title="DSARP Studio", page_icon="🧭", layout="wide")

ctx = get_ctx()

st.title("DSARP Refactoring Suggestion Studio")
st.caption("Local-first, evidence-grounded refactoring suggestions with human "
           "HGRS review and SkillOpt-style skill improvement. No cloud APIs required.")

col1, col2, col3, col4 = st.columns(4)
projects = ctx.store.list_projects()
runs = ctx.store.list_runs()
reviews = ctx.store.list_reviews()
skills = ctx.store.list_skills()
col1.metric("Projects", len(projects))
col2.metric("Agent runs", len(runs))
col3.metric("Human reviews", len(reviews))
col4.metric("Skill versions", len(skills))

st.subheader("Model endpoint")
st.code(f"provider = {ctx.cfg.model.provider}\n"
        f"base_url = {ctx.cfg.model.base_url}\n"
        f"model_id = {ctx.cfg.model.model_id}", language="ini")
health = services.check_model_endpoint(ctx)
(st.success if health["ok"] else st.error)(
    f"{'🟢' if health['ok'] else '🔴'} {health['message']}")
if not health["ok"]:
    st.caption("Agent runs will fail fast with this message until the endpoint "
               "is up. The 'mock' provider always works offline.")
st.info("Use the pages in the sidebar: 1) add a project and import tool exports, "
        "2) build evidence, 3) run agents, 4) review suggestions with HGRS, "
        "5) optimize + validate skills, 6) export the dataset.")

with st.expander("Recent audit trail"):
    for entry in ctx.store.list_audit(limit=30):
        st.text(f"{entry['at']}  {entry['entity_type']}:{entry['action']}  "
                f"{entry['entity_id']}  by {entry['actor']}")
