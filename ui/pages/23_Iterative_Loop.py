"""Iterative refactoring: repeat the closed loop until it stops helping."""
import streamlit as st
from _common import cfg, data_dir
from dsarp.util import read_json

st.title("♻️ Iterative refactoring — repeat until converged")
st.caption("One pass is conservative on purpose: refactorings that touch the same type "
           "interfere, so only one is applied and the rest are deferred. Repeating the loop "
           "re-detects on the *refactored* code, letting the deferred plans land in a later pass.")

st.info("**A pass is kept only if it still builds AND strictly reduces architectural smells.** "
        "Anything else is rolled back and the loop stops, so the result is never worse than "
        "what you started with.")

out = data_dir() / "outputs"
projects = sorted([p.name for p in out.iterdir()
                   if p.is_dir() and (p / "iterative_loop_report.json").exists()]) \
    if out.exists() else []
if not projects:
    st.warning("No iterative run yet.")
    st.code("py -m dsarp.cli refactor-iterative --repo apache-commons-validator "
            "--detector both --max-passes 4", language="bash")
    st.stop()

sel = st.selectbox("Project", projects)
rep = read_json(out / sel / "iterative_loop_report.json", default=None)
if not rep:
    st.error("Report could not be read.")
    st.stop()

st.success("**Scored on the smell types this run targeted**, not the grand total. Splitting a "
           "God Component creates a new package that Designite flags as Feature Concentration, "
           "so a refactoring that removed exactly what it aimed at can still make the overall "
           "count look worse.")

c = st.columns(4)
c[0].metric("Targeted smells",
            f"{rep.get('architectural_smells_before')} → {rep.get('architectural_smells_after')}")
c[1].metric("Removed", rep.get("removed"), delta=f"{rep.get('reduction_pct')}%")
c[2].metric("Passes accepted", f"{rep.get('passes_accepted')} / {rep.get('passes_run')}")
c[3].metric("Smell types refactored", len(rep.get("smell_types_refactored") or []))

if rep.get("smell_types_refactored"):
    st.write("**Refactored across the run:** " + ", ".join(rep["smell_types_refactored"]))

st.divider()
st.subheader("Pass-by-pass")
rows = []
for p in rep.get("passes", []):
    rows.append({
        "pass": p["pass"],
        "verified": "✅" if p.get("verification_status") == "verified" else "🔴",
        "build": p.get("build"),
        "score before → after": f"{p.get('score_before')} → {p.get('score_after')}",
        "files changed": p.get("files_changed"),
        "deferred": p.get("deferred"),
        "kept": "✅ kept" if p.get("accepted") else "↩️ rolled back",
        "refactored": ", ".join(p.get("smell_types_refactored") or []),
    })
st.dataframe(rows, use_container_width=True, hide_index=True)

traj = [p["score_before"] for p in rep.get("passes", []) if p.get("score_before") is not None]
last = [p["score_after"] for p in rep.get("passes", [])
        if p.get("accepted") and p.get("score_after") is not None]
if traj:
    st.line_chart({"architectural smells": traj + (last[-1:] if last else [])}, height=260)
    st.caption("x = pass, y = architectural smells remaining.")

pt = rep.get("per_type") or {}
if pt.get("targeted"):
    st.divider()
    st.subheader("Per smell type")
    st.markdown("**Targeted — what the refactorings aimed at**")
    st.dataframe(pt["targeted"], use_container_width=True, hide_index=True)
    if pt.get("side_effects"):
        st.markdown("**Side effects — types that moved without being targeted**")
        st.dataframe(pt["side_effects"], use_container_width=True, hide_index=True)
        st.caption("New packages created by a split commonly appear here as Feature "
                   "Concentration. That is a real trade-off, reported rather than hidden.")

if rep.get("stop_reason"):
    st.warning(f"**Stopped:** {rep['stop_reason']}")
if rep.get("refactored_source"):
    st.caption(f"Refactored source kept at `{rep['refactored_source']}` "
               "(your original checkout is never modified).")
