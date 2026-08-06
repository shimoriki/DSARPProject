import streamlit as st
from _common import list_projects, load_case

st.title("🧪 Tool Evidence")
st.caption("Loop 4: normalized Arcan / Designite / graph findings with evidence IDs & tool agreement.")

projects = list_projects()
sel = st.selectbox("Project", projects or ["(none)"])
case = load_case(sel) or {}
smells = case.get("smells", [])
st.metric("Smells", len(smells))
for s in smells:
    agree = len(s.get("tool_sources", []))
    with st.expander(f"{s.get('smell_type')} · {s.get('component_level')} · "
                     f"tools={','.join(s.get('tool_sources', []))} · agreement={agree}"):
        st.write("Affected components:", s.get("affected_components"))
        st.write("Severity:", s.get("severity"))
        st.write("Evidence IDs:", s.get("evidence_ids"))
        st.write("Metrics:", s.get("metrics"))
