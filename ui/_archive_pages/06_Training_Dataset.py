import streamlit as st
from _common import cfg
from dsarp.util import read_jsonl

st.title("📚 Training Dataset")
st.caption("Loop 7: ranker rows (candidates.jsonl) and optional LoRA chat records (chat.jsonl).")

rows = list(read_jsonl(cfg().data_dir / "training" / "candidates.jsonl"))
st.metric("Ranker examples", len(rows))
if rows:
    pos = sum(r.get("label", 0) for r in rows)
    c = st.columns(3)
    c[0].metric("Positive", pos)
    c[1].metric("Negative", len(rows) - pos)
    by = {}
    for r in rows:
        by[r.get("smell_type", "?")] = by.get(r.get("smell_type", "?"), 0) + 1
    c[2].metric("Smell types", len(by))
    st.subheader("Distribution by smell type")
    st.bar_chart(by)
    st.subheader("Sample records (masked)")
    st.json(rows[:5])
else:
    st.info("No dataset yet. Build aligned examples then run `dsarp-local ranker train`.")
