"""One smell type per pass — which types actually pay off, per repository.

A mixed pass refactors several smell types at once, so when the count drops nothing says
which type did it, and a type that quietly makes things worse hides behind the ones that
help. This page reads the per-smell surveys, where each pass targets exactly one type, so
every row is a statement about that type on that repository.
"""
import glob
from pathlib import Path

import streamlit as st
from _common import cfg, data_dir
from dsarp.util import read_json

st.title("🔬 One smell type per pass")
st.caption("Each pass targets a single smell type and is kept only if it measurably reduced "
           "smells while still compiling. Types that create structure before they pay off "
           "(God Component, Insufficient/Broken Modularization) get a consecutive second "
           "pass to consolidate.")

reports = sorted(glob.glob(str(data_dir() / "outputs" / "*__bysmell*" /
                               "iterative_loop_report.json")))
if not reports:
    st.info("No per-smell survey has been run yet.")
    st.code("py -m dsarp.cli refactor-iterative --repo apache-struts "
            "--detector both --by-smell", language="bash")
    st.stop()

rows, per_repo = [], []
for f in reports:
    r = read_json(Path(f))
    if not r:
        continue
    repo = r.get("project_id", Path(f).parent.name)
    per_repo.append({
        "repository": repo,
        "passes kept": f"{r.get('passes_accepted')}/{r.get('passes_run')}",
        "smells before": r.get("architectural_smells_before"),
        "smells after": r.get("architectural_smells_after"),
        "reduction %": r.get("reduction_pct"),
    })
    for p in r.get("passes") or []:
        targeted = ", ".join(p.get("smell_types_refactored") or []) or "—"
        rows.append({
            "repository": repo, "pass": p.get("pass"), "smell type": targeted,
            "build": p.get("build"), "score before": p.get("score_before"),
            "score after": p.get("score_after"),
            "kept": "✅" if p.get("accepted") else "↩︎ rolled back",
        })

st.subheader("Per repository")
st.dataframe(per_repo, use_container_width=True, hide_index=True)

st.subheader("Per pass — one smell type each")
st.dataframe(rows, use_container_width=True, hide_index=True)

kept = [r for r in rows if r["kept"].startswith("✅")]
if kept:
    st.success("**Types that paid off:** " +
               ", ".join(sorted({r['smell type'] for r in kept})) +
               ". Each was measured alone, so the reduction is attributable to that type "
               "rather than to a mixture.")
rolled = sorted({r["smell type"] for r in rows if not r["kept"].startswith("✅")}
                - {r["smell type"] for r in kept})
if rolled:
    st.warning("**Types that did not pay off here:** " + ", ".join(rolled) +
               ". They compiled or were rolled back cleanly, and the run continued to the "
               "next type — an unhelpful type is the answer for that type, not a reason to "
               "abandon the rest.")
