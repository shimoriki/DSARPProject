import difflib
import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _bootstrap import get_ctx  # noqa: E402
from dsarp import services  # noqa: E402
from dsarp.skillopt.digest import build_digest  # noqa: E402

st.set_page_config(page_title="Skill Optimization", layout="wide")
ctx = get_ctx()
st.title("6 · Skill Optimization (SkillOpt loop)")
st.caption("Text-space optimization of reusable skills from aggregated human "
           "reviews. This never trains model weights and never overwrites the "
           "production skill.")

skills = ctx.store.list_skills()
if not skills:
    st.info("No skills registered.")
    st.stop()

st.dataframe(skills, use_container_width=True)

names = sorted({s["name"] for s in skills})
name = st.selectbox("Skill", names)
versions = [s["version"] for s in skills if s["name"] == name]
version = st.selectbox("Version to improve", versions)

col1, col2 = st.columns(2)

with col1:
    st.subheader("Feedback digest")
    if st.button("Build digest from completed reviews"):
        try:
            st.session_state["digest"] = build_digest(ctx.store, name, version)
        except ValueError as exc:
            st.error(str(exc))
    if "digest" in st.session_state:
        st.json(st.session_state["digest"])
    else:
        digests = ctx.store.list_digests(name)
        if digests:
            st.caption("Latest stored digest:")
            st.json(json.loads(digests[0]["digest_json"]))

with col2:
    st.subheader("Generate candidate skill")
    st.caption("The optimizer agent proposes a revised skill saved as "
               f"skills/{name}_vN_candidate.md")
    if st.button("Run optimizer"):
        try:
            with st.spinner("Optimizing skill with local model..."):
                result = services.optimize(ctx, name, version)
            st.success(result)
            st.session_state["candidate"] = result
        except Exception as exc:
            st.error(str(exc))

st.divider()
st.subheader("Compare versions")
va = st.selectbox("Version A", versions, key="va")
vb = st.selectbox("Version B", versions,
                  index=len(versions) - 1, key="vb")
if va != vb:
    rowa = ctx.store.get_skill(name, va)
    rowb = ctx.store.get_skill(name, vb)
    ta = ctx.cfg.resolve(rowa["file_path"]).read_text(encoding="utf-8").splitlines()
    tb = ctx.cfg.resolve(rowb["file_path"]).read_text(encoding="utf-8").splitlines()
    diff = "\n".join(difflib.unified_diff(ta, tb, fromfile=va, tofile=vb, lineterm=""))
    st.code(diff or "(identical)", language="diff")
