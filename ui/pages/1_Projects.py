import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _bootstrap import get_ctx  # noqa: E402
from dsarp import services  # noqa: E402
from dsarp.registry import ARCHITECTURE_TYPES, COMPONENT_TYPES  # noqa: E402

st.set_page_config(page_title="Projects", layout="wide")
ctx = get_ctx()
st.title("1 · Projects")

with st.form("add_project"):
    st.subheader("Add project")
    name = st.text_input("Name", placeholder="tika")
    path = st.text_input("Local repository path (for execute mode / source inspection)")
    arch = st.selectbox("Architecture type", ARCHITECTURE_TYPES)
    ctype = st.selectbox("Component type", COMPONENT_TYPES)
    revision = st.text_input("Source revision (optional git commit)")
    if st.form_submit_button("Add") and name:
        services.add_project(ctx, name, path, arch, ctype, revision or None)
        st.success(f"Project '{name}' added.")
        st.rerun()

st.subheader("Existing projects")
projects = ctx.store.list_projects()
if projects:
    st.dataframe(projects, use_container_width=True)
else:
    st.info("No projects yet.")

st.divider()
st.subheader("Import tool export (import mode)")
if projects:
    with st.form("import_file"):
        pname = st.selectbox("Project", [p["name"] for p in projects])
        tool = st.selectbox("Tool adapter", ["arcan", "designite", "static_graph"])
        fpath = st.text_input("Path to export file (CSV/JSON/DOT)",
                              placeholder="sample_data/tika/arcan/ArchitectureSmells.csv")
        if st.form_submit_button("Import") and fpath:
            try:
                summary = services.import_tool_file(ctx, pname, tool, fpath)
                st.success(summary)
            except Exception as exc:
                st.error(str(exc))

    st.subheader("Run local tools (execute mode)")
    st.caption("Runs the shell commands configured in config/config.yaml. "
               "You must have legal local access to Arcan / Designite; DSARP "
               "ships no proprietary binaries.")
    with st.form("analyze"):
        pname2 = st.selectbox("Project ", [p["name"] for p in projects])
        tools = st.multiselect("Tools", list(ctx.cfg.tools.keys()) or ["arcan", "designite"])
        if st.form_submit_button("Run analysis") and tools:
            try:
                st.json(services.analyze_project(ctx, pname2, tools))
            except Exception as exc:
                st.error(str(exc))

    st.subheader("Build normalized evidence")
    with st.form("build_evidence"):
        pname3 = st.selectbox("Project  ", [p["name"] for p in projects])
        if st.form_submit_button("Build evidence"):
            try:
                n = services.rebuild_evidence(ctx, pname3)
                st.success(f"Built {n} evidence cases.")
            except Exception as exc:
                st.error(str(exc))
