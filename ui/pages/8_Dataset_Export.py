import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _bootstrap import get_ctx  # noqa: E402
from dsarp import services  # noqa: E402

st.set_page_config(page_title="Dataset Export", layout="wide")
ctx = get_ctx()
st.title("8 · Dataset Export")

st.markdown("""
**Skill optimization** (default loop) updates prompts and reusable agent skills —
cheap, reviewable, reversible.
**Fine-tuning** is an optional later stage that changes model weights and
requires a sufficiently large, human-reviewed dataset. Nothing on this page
trains a model.
""")

reviews = ctx.store.list_reviews()
st.metric("Total human reviews", len(reviews))
if reviews:
    df = pd.DataFrame(reviews)
    st.bar_chart(df["hgrs"].value_counts().sort_index())

with st.form("export"):
    min_hgrs = st.slider("Minimum HGRS for export", 1.0, 5.0, 4.0, 0.1)
    projects = [p["name"] for p in ctx.store.list_projects()]
    project = st.selectbox("Project filter", ["(all)"] + projects)
    formats = st.multiselect("Formats", ["instruction", "chat", "csv"],
                             default=["instruction", "chat", "csv"])
    lora = st.checkbox("Also write LoRA preparation folder (no training runs)")
    if st.form_submit_button("Export reviewed high-quality examples"):
        try:
            result = services.export_dataset(
                ctx, min_hgrs, None if project == "(all)" else project,
                formats, lora)
            st.success(f"Exported {result['examples']} examples to {result['out_dir']}")
            st.json(result)
        except ValueError as exc:
            st.error(str(exc))

st.divider()
st.subheader("Comparison table (experiment mode)")
projects = [p["name"] for p in ctx.store.list_projects()]
if projects:
    proj = st.selectbox("Project", ["(all)"] + projects, key="cmp_proj")
    table = services.comparison_table(
        ctx, None if proj == "(all)" else proj)
    if table:
        st.dataframe(pd.DataFrame(table), use_container_width=True)
    else:
        st.info("No runs to compare yet.")
