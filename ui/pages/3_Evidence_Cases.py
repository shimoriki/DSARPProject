import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _bootstrap import get_ctx, project_selector  # noqa: E402
from dsarp import services  # noqa: E402

st.set_page_config(page_title="Evidence Cases", layout="wide")
ctx = get_ctx()
st.title("3 · Evidence Cases")

pname = project_selector(ctx)
if pname:
    cases = ctx.store.list_cases(project_id=pname)
    if not cases:
        st.info("No evidence cases — build evidence on the Projects page.")
    else:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.dataframe(cases, use_container_width=True)
        with col2:
            st.metric("Total cases", len(cases))
            st.metric("Train", sum(1 for c in cases if c["split"] == "train"))
            st.metric("Validation", sum(1 for c in cases if c["split"] == "validation"))
            if st.button("Assign train/validation split"):
                counts = services.split_evidence(ctx, pname)
                st.success(counts)
                st.rerun()

        case_id = st.selectbox(
            "Inspect case",
            [c["id"] for c in cases],
            format_func=lambda cid: next(
                f"{c['smell_id']} · {c['smell_type']}" for c in cases if c["id"] == cid))
        case = ctx.store.get_case(case_id)
        if case:
            st.subheader(f"{case.smell_id} — {case.smell_type}")
            st.caption(f"split: {next(c['split'] for c in cases if c['id'] == case_id)} · "
                       f"architecture: {case.architecture_type} · "
                       f"component type: {case.component_type.value}")
            if case.limitations:
                st.warning("Limitations:\n\n- " + "\n- ".join(case.limitations))
            st.json(case.public_dict())
