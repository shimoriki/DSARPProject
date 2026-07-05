import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _bootstrap import get_ctx, project_selector  # noqa: E402
from dsarp import services  # noqa: E402

st.set_page_config(page_title="Validation Results", layout="wide")
ctx = get_ctx()
st.title("7 · Held-out Validation & Promotion")
st.caption("Candidates run against the baseline on validation-split cases. "
           "Promotion needs: ΔHGRS ≥ threshold, no grounding drop, zero "
           "critical hallucinations, AND recorded human approval.")

pname = project_selector(ctx)
skills = ctx.store.list_skills()
names = sorted({s["name"] for s in skills})

if pname and names:
    with st.form("validate"):
        name = st.selectbox("Skill", names)
        versions = [s["version"] for s in skills if s["name"] == name]
        v0 = st.selectbox("Baseline version", versions)
        v1 = st.selectbox("Candidate version", versions,
                          index=len(versions) - 1)
        if st.form_submit_button("Run held-out validation"):
            try:
                with st.spinner("Running both versions on validation cases..."):
                    report = services.validate(ctx, pname, name, v0, v1)
                st.session_state["last_report"] = report
            except Exception as exc:
                st.error(str(exc))

if "last_report" in st.session_state:
    report = st.session_state["last_report"]
    st.subheader("Latest validation report")
    ok = report["passed"]
    st.markdown(f"**Gate:** {'✅ PASSED' if ok else '❌ FAILED'}  ·  "
                f"ΔHGRS = {report['hgrs_improvement']}  ·  "
                f"Δgrounding = {report['grounding_delta']}")
    if report["fail_reasons"]:
        st.error("\n".join(report["fail_reasons"]))
    st.info(report["note"])
    st.json(report)

st.divider()
st.subheader("All validation reports")
reports = ctx.store.list_validation_reports()
if not reports:
    st.info("No validation reports yet.")
for r in reports:
    body = json.loads(r["report_json"])
    label = (f"{r['created_at']} · {r['skill_name']}: {r['baseline_version']} vs "
             f"{r['candidate_version']} · "
             f"{'PASSED' if r['passed'] else 'failed'}"
             f"{' · PROMOTED' if r['promoted'] else ''}")
    with st.expander(label):
        st.json(body)
        if r["passed"] and not r["promoted"]:
            st.warning("Human approval required before promotion.")
            approver = st.text_input("Approver id", value=ctx.cfg.reviewer_id,
                                     key=f"appr_{r['id']}")
            if st.button("Approve and promote", key=f"promote_{r['id']}"):
                try:
                    result = services.approve_and_promote(ctx, r["id"], approver)
                    st.success(result)
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
