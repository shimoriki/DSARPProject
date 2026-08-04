import streamlit as st
from _common import cfg, list_projects
from dsarp.util import read_json

st.title("🔧 RefactoringMiner Events")
st.caption("Loop 3: historical refactorings mined from training repos.")

projects = list_projects()
sel = st.selectbox("Project", projects or ["(none)"])
events = read_json(cfg().data_dir / "refactoring_events" / f"{sel}.json", default=[]) or []
if not events:
    st.info("No imported RefactoringMiner events for this project. "
            "Import a RefactoringMiner JSON export into data/refactoring_events/<project>.json.")
else:
    st.write(f"{len(events)} events")
    for e in events[:200]:
        with st.expander(f"{e.get('refactoring_type')} @ {str(e.get('commit_sha'))[:10]}"):
            st.write("Before:", e.get("before_entity"))
            st.write("After:", e.get("after_entity"))
            st.write("Files:", e.get("file_paths"))
            st.write("Components:", e.get("affected_components"))
            st.caption(e.get("description", ""))
