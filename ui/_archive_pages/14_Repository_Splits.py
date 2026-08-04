import streamlit as st
from dsarp.splits.manager import SplitManager, LeakageError

st.title("🔀 Repository Splits")
st.caption("Repository-level splits with leakage guard. Cassandra = unseen test only.")

sm = SplitManager()
try:
    sm.assert_no_leakage()
    st.success("✅ Leakage guard passed — no test/unseen repo appears in training.")
except LeakageError as e:
    st.error(f"🔴 Leakage detected: {e}")

rows = []
for split, members in [("train", sm.train), ("validation", sm.validation),
                       ("test", sm.test), ("unseen", sm.unseen)]:
    for m in members:
        rows.append({"repository": m, "split": split,
                     "trainable": sm.is_training_allowed(m)})
st.table(rows)

st.subheader("Leave-one-repository-out folds")
for f in sm.loro_folds():
    st.write(f"- Hold out **{f.held_out}** → train on {len(f.train)} repos")
