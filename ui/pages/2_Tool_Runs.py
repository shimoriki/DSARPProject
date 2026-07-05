import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _bootstrap import get_ctx, project_selector  # noqa: E402

st.set_page_config(page_title="Tool Runs", layout="wide")
ctx = get_ctx()
st.title("2 · Tool Runs")

pname = project_selector(ctx)
if pname:
    project = ctx.store.get_project(pname)
    runs = ctx.store.list_tool_runs(project["id"])
    if not runs:
        st.info("No tool runs for this project yet — import a file on the Projects page.")
    else:
        st.dataframe(
            [{k: r[k] for k in ("id", "tool", "mode", "status", "source_path",
                                "source_hash", "started_at", "finished_at", "error")}
             for r in runs],
            use_container_width=True)
        run_id = st.selectbox("Inspect raw findings of run",
                              [r["id"] for r in runs])
        findings = ctx.store.raw_findings_for_run(run_id)
        st.caption(f"{len(findings)} raw records (kept verbatim, separate from "
                   "normalized evidence)")
        for f in findings[:200]:
            with st.expander(f"{f['kind']} · {f['tool_record_id']} · {f['raw_source_file']}"):
                st.json(json.loads(f["record_json"]))
