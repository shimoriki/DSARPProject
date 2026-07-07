import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _bootstrap import get_ctx  # noqa: E402

st.set_page_config(page_title="Activity Log", layout="wide")
ctx = get_ctx()
st.title("9 · Activity Log")
st.caption("Complete audit trail: every import, evidence build, agent run, "
           "human review, skill change, validation, and export — nothing is "
           "hidden or deleted.")

limit = st.select_slider("Entries to load", [200, 500, 1000, 2000, 5000], value=500)
entries = ctx.store.list_audit(limit=limit)
if not entries:
    st.info("No activity recorded yet.")
    st.stop()

types = sorted({e["entity_type"] for e in entries})
col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    selected_types = st.multiselect("Entity type", types, default=types)
with col2:
    actors = sorted({e["actor"] for e in entries if e["actor"]})
    selected_actors = st.multiselect("Actor", actors, default=actors)
with col3:
    search = st.text_input("Search (action / id / details)")

filtered = [
    e for e in entries
    if e["entity_type"] in selected_types
    and (e["actor"] in selected_actors or not e["actor"])
    and (not search or search.lower() in
         f"{e['action']} {e['entity_id']} {e['details_json']}".lower())
]
st.metric("Entries shown", f"{len(filtered)} / {len(entries)}")

df = pd.DataFrame([{k: e[k] for k in ("at", "entity_type", "action",
                                      "entity_id", "actor")} for e in filtered])
st.dataframe(df, use_container_width=True, height=400)

st.subheader("Details (latest 25 shown)")
for e in filtered[:25]:
    details = json.loads(e["details_json"] or "{}")
    with st.expander(f"{e['at']} · {e['entity_type']}:{e['action']} · "
                     f"{(e['entity_id'] or '')[:40]} · by {e['actor']}"):
        st.json(details if details else {"details": "none recorded"})
