import streamlit as st
from _common import cfg
from dsarp.util import read_json

st.title("🌍 Generalisation Report")
st.caption("Cross-repository generalisation. Cassandra is unseen-test only.")

rep = read_json(cfg().data_dir / "reports" / "generalisation_report.json", default={}) or {}
if not rep:
    st.info("No report yet. Run: `dsarp-local generalisation report`")
    st.stop()

cc = st.columns(3)
cc[0].metric("Train repos", len(rep.get("training_repositories", [])))
cc[1].metric("Validation repos", len(rep.get("validation_repositories", [])))
cc[2].metric("LORO mean", rep.get("loro_mean_validation_score"))

st.subheader("Splits")
st.json(rep.get("splits", {}))

if rep.get("examples_per_repository"):
    st.subheader("Examples per repository")
    st.bar_chart(rep["examples_per_repository"])

st.subheader("Type generalisation")
st.json(rep.get("type_generalisation", {}))

st.subheader("Per-repository quality")
if rep.get("per_repository_quality"):
    st.table(rep["per_repository_quality"])
