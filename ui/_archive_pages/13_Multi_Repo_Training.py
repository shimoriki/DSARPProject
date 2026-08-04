import streamlit as st
from _common import cfg
from dsarp.util import read_json, read_jsonl

st.title("🗂️ Multi-Repository Training")
st.caption("Repository-independent dataset + ranker. No raw package names in training.")

c = cfg()
stats = read_json(c.data_dir / "reports" / "multi_repo_dataset_stats.json", default={}) or {}
report = read_json(c.data_dir / "models" / "ranker_report.json", default={}) or {}
meta = report.get("metadata", {})

col = st.columns(4)
col[0].metric("Examples", stats.get("examples", 0))
col[1].metric("Repositories", stats.get("repositories", 0))
col[2].metric("Positives", stats.get("positive", 0))
col[3].metric("Ranker backend", meta.get("backend", "—"))

if stats.get("by_repository"):
    st.subheader("Examples per repository")
    st.bar_chart(stats["by_repository"])
if stats.get("by_smell_type"):
    st.subheader("Smell distribution")
    st.bar_chart(stats["by_smell_type"])
if stats.get("by_refactoring_type"):
    st.subheader("Refactoring type distribution")
    st.bar_chart(stats["by_refactoring_type"])

st.subheader("Ranker metadata")
st.json(meta)

fi = report.get("feature_importance", {})
if fi:
    st.subheader("Feature importance (repo-independent features)")
    st.bar_chart(dict(sorted(fi.items(), key=lambda kv: -kv[1])[:12]))

st.subheader("Sample training rows (masked, structural only)")
rows = list(read_jsonl(c.data_dir / "training" / "multi_repo_train_candidates.jsonl"))[:3]
st.json(rows)
st.caption("Run: `dsarp-local dataset build-multi-repo` then `dsarp-local ranker train "
           "--dataset data/training/multi_repo_train_candidates.jsonl`")
