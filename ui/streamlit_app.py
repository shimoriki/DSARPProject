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

st.info("👉  Start on **📌 Presentation Summary** (left sidebar) — the whole MVP in one view. "
        "To run the pipeline yourself, use **🚀 Analyze a Repository**.")

st.divider()
st.subheader("Verified results")
st.caption("Measured by running Arcan and DesigniteJava before AND after a real OpenRewrite "
           "refactoring, on a build that still compiles. A pass that breaks the build is "
           "rolled back, so these are floors rather than best cases.")
c = st.columns(3)
c[0].metric("commons-validator", "18.4%", "76 → 62, reproduced 3×")
c[1].metric("apache/pdfbox (unseen)", "2.2%", "1782 → 1743, from scratch")
c[2].metric("commons-io", "11.0%", "328 → 292, six smell types")

st.markdown("""
Earlier versions of this page reported figures such as *"fully untangled"* from a
**graph-only estimate** — smells recounted from the dependency graph rather than re-measured
by the tools. Those numbers did not survive tool verification and have been removed. The
figures above are the ones two real detectors agree on.
""")

st.divider()
st.markdown(
    "**Pages:** 📌 Presentation Summary · 🔬 One smell type per pass · 📈 What actually works · "
    "🚀 Analyze a Repository · Real Tool Loop · Iterative Loop · Dependency Graphs · "
    "Suggestions · OpenRewrite Recipes · How It Works · MVP Results.")
st.caption("Arcan 1.2.1 on compiled bytecode + DesigniteJava on source · OpenRewrite "
           "`mvn rewrite:run` performs the change · no cloud APIs required · "
           "82 automated tests (`py -m pytest -q`).")
