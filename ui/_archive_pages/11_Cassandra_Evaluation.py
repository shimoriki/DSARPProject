import streamlit as st
from _common import load_report, load_suggestions

st.title("🎯 Cassandra Final Evaluation")
st.caption("apache/cassandra is the ONLY unseen test repo — never used in training/tuning/ranking/LoRA.")

pid = "apache-cassandra"
rep = load_report(pid)
sugs = load_suggestions(pid)
if not rep:
    st.info("No Cassandra evaluation yet. Run:\n\n"
            "```\ndsarp-local evaluate --repo apache-cassandra\n```")
else:
    c = st.columns(4)
    c[0].metric("Smells", rep.get("num_smells"))
    c[1].metric("Suggestions", rep.get("num_suggestions"))
    c[2].metric("Grounding pass", rep.get("evidence_grounding_pass_rate"))
    c[3].metric("Hallucinations", rep.get("hallucination_failure_count"))
    c2 = st.columns(3)
    c2[0].metric("JSON validity", rep.get("json_validity_rate"))
    c2[1].metric("Recipe drafts", rep.get("recipe_draft_count"))
    c2[2].metric("Recipe validated", rep.get("recipe_validation_count"))
    st.subheader("Token optimisation")
    st.json(rep.get("token_optimisation", {}))
    st.subheader("Top suggestions")
    st.table(rep.get("top_suggestions", []))
