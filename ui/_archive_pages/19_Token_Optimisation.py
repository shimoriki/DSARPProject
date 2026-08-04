import streamlit as st
from _common import cfg, list_projects, load_report
from dsarp.util import read_jsonl

st.title("🪙 Token Optimisation Report")
st.caption("Cache hits, model calls avoided, and estimated tokens saved (token layer).")

projects = list_projects()
sel = st.selectbox("Project", projects or ["(none)"])
rep = load_report(sel).get("token_optimisation", {})
if rep:
    c = st.columns(4)
    c[0].metric("Model calls", rep.get("total_model_calls"))
    c[1].metric("Cache hits", rep.get("cache_hits"))
    c[2].metric("Cache misses", rep.get("cache_misses"))
    c[3].metric("Est. tokens saved", rep.get("estimated_tokens_saved"))
    st.json(rep)
else:
    st.info("No token report for this project yet.")

st.subheader("Per-call usage log (last 20)")
rows = list(read_jsonl(cfg().data_dir / "outputs" / "token_usage.jsonl"))[-20:]
if rows:
    st.table([{"task": r.get("task_type"), "model": r.get("model_id"),
               "in_est": r.get("input_token_estimate"),
               "prompt": r.get("actual_prompt_tokens"),
               "completion": r.get("actual_completion_tokens"),
               "cache_hit": r.get("cache_hit")} for r in rows])
else:
    st.caption("No usage log yet.")
