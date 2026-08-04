import streamlit as st
from _common import cfg, data_dir
from dsarp.util import read_json

st.title("🔬 Refactoring Verification (closed loop)")
st.caption("What actually changed after executing a suggestion: apply the refactoring, then "
           "re-measure the architectural smells. Move Class is source-applied; design-heavy "
           "refactorings (Extract Interface / Dependency Inversion) are graph-simulated.")

out = data_dir() / "outputs"
_cand = [p.name for p in out.iterdir()
         if p.is_dir() and ((p / "verify_effect.json").exists()
                            or (p / "verify_cumulative.json").exists())] if out.exists() else []
# show repos WITH the cumulative trajectory first (richest view lands by default)
projects = sorted(_cand, key=lambda n: (not (out / n / "verify_cumulative.json").exists(), n))
if not projects:
    st.info("No verification runs yet. Run:\n\n"
            "```\ndsarp-local verify-effect --repo <name>\n"
            "dsarp-local verify-effect --repo <name> --cumulative --top-k 60\n```")
    st.stop()

sel = st.selectbox("Project", projects)

# --------------------------------------------------------------------------- #
# Per-suggestion effect
# --------------------------------------------------------------------------- #
eff = read_json(out / sel / "verify_effect.json", default=[]) or []
if eff:
    st.subheader("Per-suggestion effect (before → after)")
    removed = sum(1 for r in eff if r.get("smell_removed"))
    c = st.columns(3)
    c[0].metric("Suggestions tested", len(eff))
    c[1].metric("Measurably removed a smell", removed)
    c[2].metric("Baseline cycles", eff[0].get("cycles_before", "—"))

    rows = []
    for r in eff:
        if r.get("applied"):
            how = (f"move {r['break_cycle']['count']} classes ({r['break_cycle']['direction_removed']})"
                   if r.get("break_cycle") else
                   f"{r.get('move', {}).get('class_fqn','')} → {r.get('move', {}).get('to_package','')}")
            method = f"source-applied ({r.get('applier')})"
        elif r.get("simulated"):
            how = f"break {r.get('simulation', {}).get('edge_targeted','')}"
            method = "graph-simulation"
        else:
            how, method = r.get("note", ""), "not tested"
        rows.append({
            "refactoring": r.get("refactoring"),
            "smell": r.get("smell_type", ""),
            "how": how, "method": method,
            "cycles before→after": f"{r.get('cycles_before','?')} → {r.get('cycles_after','?')}",
            "result": "✅ removed" if r.get("smell_removed") else "— no change",
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption("✅ = re-measuring the dependency graph after the change shows the smell is gone.")

# --------------------------------------------------------------------------- #
# Cumulative multi-step trajectory
# --------------------------------------------------------------------------- #
cum = read_json(out / sel / "verify_cumulative.json", default=None)
if cum:
    st.divider()
    st.subheader("Cumulative multi-step effect")
    st.caption("Apply the top-N suggestions together and watch the tangle shrink. Metric = packages "
               "still in a dependency cycle (largest strongly-connected core), which — unlike raw "
               "cycle count — does not saturate on dense graphs.")
    c = st.columns(4)
    c[0].metric("Refactorings applied", cum.get("steps"))
    c[1].metric("Packages in cycles", f"{cum.get('packages_in_cycles_before')} → "
                                      f"{cum.get('packages_in_cycles_after')}")
    c[2].metric("Freed", f"{cum.get('packages_freed')} ({cum.get('reduction_pct')}%)")
    c[3].metric("Core tangle (SCC)", f"{cum.get('largest_tangle_before')} → "
                                     f"{cum.get('largest_tangle_after')} pkgs")

    traj = cum.get("trajectory", [])
    if traj:
        chart = {"packages in cycles": [p["packages_in_cycles"] for p in traj],
                 "largest tangle": [p["largest_tangle"] for p in traj]}
        st.line_chart(chart, height=280)
        st.caption("x = number of suggestions applied (step); y = packages still tangled.")
        with st.expander("Step-by-step edges broken"):
            st.dataframe([{"step": p["step"], "refactoring": p.get("refactoring") or "(baseline)",
                           "edge broken": p.get("edge") or "—",
                           "packages in cycles": p["packages_in_cycles"],
                           "largest tangle": p["largest_tangle"]} for p in traj],
                         use_container_width=True, hide_index=True)

    if cum.get("largest_tangle_after", 0) > 5:
        st.warning(f"An irreducible core of {cum['largest_tangle_after']} mutually-cyclic packages "
                   "remains — boundary refactorings can't break it; deeper restructuring is needed.")
    elif cum.get("packages_in_cycles_after") == 0:
        st.success("The suggestions fully untangled this repository (0 packages left in cycles).")
