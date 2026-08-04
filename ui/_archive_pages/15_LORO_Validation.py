import streamlit as st
from _common import cfg
from dsarp.util import read_json

st.title("🎯 Leave-One-Repository-Out Validation")
st.caption("Generalisation to a held-out repository (repository-level, not row-shuffle).")

loro = read_json(cfg().data_dir / "models" / "loro_report.json", default={}) or {}
if not loro:
    st.info("No LORO report yet. Run: `dsarp-local validate leave-one-repo-out`")
else:
    st.metric("Mean validation score", loro.get("mean_validation_score"))
    st.table([{"held_out": f["held_out"], "train_count": f["train_count"],
               "val_count": f["val_count"], "train_score": f["train_score"],
               "validation_score": f["validation_score"],
               "overfitting": "⚠️" if f["overfitting_warning"] else "ok"}
              for f in loro.get("folds", [])])
    scores = {f["held_out"]: f["validation_score"] or 0 for f in loro.get("folds", [])}
    if scores:
        st.subheader("Validation score by held-out repository")
        st.bar_chart(scores)
