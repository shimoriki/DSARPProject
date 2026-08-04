import streamlit as st
from _common import cfg, list_projects, load_report
from dsarp.util import read_jsonl

st.title("📊 Reports")
st.caption("Loop 13: quality, grounding, hallucination, recipe & token metrics across projects.")

projects = list_projects()
rows = []
for p in projects:
    rep = load_report(p)
    if rep:
        rows.append({
            "project": p,
            "suggestions": rep.get("num_suggestions"),
            "grounding_pass": rep.get("evidence_grounding_pass_rate"),
            "hallucinations": rep.get("hallucination_failure_count"),
            "json_validity": rep.get("json_validity_rate"),
            "recipe_drafts": rep.get("recipe_draft_count"),
            "cache_hits": rep.get("token_optimisation", {}).get("cache_hits"),
        })
if rows:
    st.table(rows)
else:
    st.info("No reports yet.")

sel = st.selectbox("Detail for project", projects or ["(none)"])
if sel and sel != "(none)":
    st.subheader("Full report")
    st.json(load_report(sel))
    st.subheader("HGRS reviews")
    revs = list(read_jsonl(cfg().data_dir / "outputs" / sel / "hgrs_reviews.jsonl"))
    if revs:
        mean = sum(r["weighted_score"] for r in revs) / len(revs)
        st.metric("Mean HGRS", round(mean, 3))
        st.table([{"suggestion": r["suggestion_id"][:8], "hgrs": r["weighted_score"],
                   "reviewer": r["reviewer"]} for r in revs[-20:]])
    else:
        st.caption("No human reviews recorded yet.")
