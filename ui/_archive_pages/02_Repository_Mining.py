import streamlit as st
from _common import cfg, list_projects
from dsarp.repositories.manager import RepositoryManager
from dsarp.util import read_json

st.title("⛏️ Repository Mining")
st.caption("Loop 1-2: repository acquisition & commit selection. Import-mode safe (no JVM).")

projects = list_projects()
sel = st.selectbox("Project", projects or ["(none)"])
rm = RepositoryManager(cfg().data_dir)
if sel and sel != "(none)":
    slug = sel.replace("apache-", "apache/").replace("google-", "google/")
    st.write("Repo dir:", str(rm.path_for(sel)))
    commits = rm.list_commits(sel, limit=30)
    if commits:
        st.write(f"{len(commits)} recent commits")
        st.code("\n".join(commits[:30]))
    else:
        st.info("Repository not cloned locally (offline mode). "
                "RefactoringMiner events shown on the next page use imported JSON.")
    events = read_json(cfg().data_dir / "refactoring_events" / f"{sel}.json", default=[])
    st.metric("Imported RefactoringMiner events", len(events or []))
