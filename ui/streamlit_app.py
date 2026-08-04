"""DSARP dashboard — home. Focused on: analyze any repo end-to-end.

Run: `streamlit run ui/streamlit_app.py` (or `dsarp-local ui`).
"""
from __future__ import annotations

import streamlit as st

from _common import cfg, data_dir
from dsarp.util import read_json

st.set_page_config(page_title="DSARP Refactoring Agent", page_icon="🧭", layout="wide")

st.title("🧭 DSARP Evidence-Based Refactoring Agent")
st.caption("Detect architectural smells → suggest refactorings → generate OpenRewrite recipes → "
           "apply → re-detect to verify removal. Evidence-grounded, no-hallucination.")

st.info("👉  Start on the **🚀 Analyze a Repository** page (left sidebar): paste a GitHub URL and "
        "run the whole pipeline end-to-end, with the result shown at every step.")

# recent end-to-end analyses
out = data_dir() / "outputs"
reports = []
if out.exists():
    for p in sorted(out.iterdir()):
        r = read_json(p / "e2e_report.json") if p.is_dir() else None
        if r:
            reports.append(r)

st.divider()
st.subheader("Recent analyses")
if not reports:
    st.write("No end-to-end analyses yet — head to **Analyze a Repository**.")
for r in reports[-6:]:
    steps = {s["step"]: s for s in r.get("steps", [])}
    detect = steps.get(2, {}).get("summary", "")
    verdict = steps.get(8, {}).get("summary", "")
    with st.expander(f"📦 {r['project_id']} — {verdict[:80] or 'analyzed'}"):
        c = st.columns(2)
        c[0].write(f"**Detect:** {detect}")
        c[1].write(f"**Verdict:** {verdict}")
        st.caption(f"Build system: {r.get('build_system')} · {len(r.get('steps', []))} steps recorded")

st.divider()
st.markdown(
    "**Pages:** 🚀 Analyze a Repository · Tool Evidence (Arcan/Designite) · Dependency Graphs · "
    "Suggestions · OpenRewrite Recipes · Refactoring Verification · Human Review (HGRS) · Reports.")
st.caption("No cloud APIs by default · smells re-measured from the dependency graph · "
           "OpenRewrite recipes generated (run needs Maven) · Arcan used where its output is available.")
