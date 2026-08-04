import base64
import streamlit as st
from pathlib import Path
from _common import cfg, data_dir
from dsarp.repositories.manager import slug_to_dirname
from dsarp.util import read_json


def _slice_graph_html(edges, focus, removed, hops=1, height=380):
    """A readable pyvis slice around the broken edges; removed edges drawn red."""
    import networkx as nx
    from pyvis.network import Network
    g = nx.DiGraph()
    for e in edges:
        g.add_edge(e["source"], e["target"])
    keep = set(f for f in focus if f in g)
    frontier = set(keep)
    for _ in range(hops):
        nxt = set()
        for n in frontier:
            nxt.update(g.successors(n)); nxt.update(g.predecessors(n))
        keep.update(nxt); frontier = nxt
    sub = g.subgraph(list(keep)[:60])  # cap for readability
    net = Network(height=f"{height}px", directed=True, bgcolor="#ffffff", font_color="#222")
    for n in sub.nodes():
        net.add_node(n, label=n.split(".")[-1], title=n)
    for u, v in sub.edges():
        red = f"{u}->{v}" in removed
        net.add_edge(u, v, color="#ef4444" if red else "#c0c0c0", width=3 if red else 1)
    html = net.generate_html(notebook=False)
    return "data:text/html;base64," + base64.b64encode(html.encode("utf-8")).decode()


def _render_graph_before_after(project_id):
    gba = read_json(data_dir() / "outputs" / project_id / "graph_before_after.json")
    if not gba:
        return
    st.divider()
    st.subheader("🕸️ Dependency graph — before vs after refactoring")
    b, a = gba["before"]["metrics"], gba["after"]["metrics"]
    m = st.columns(4)
    m[0].metric("Edges", f"{b['edges']} → {a['edges']}", delta=a["edges"] - b["edges"])
    m[1].metric("Packages in cycles", f"{b['packages_in_cycles']} → {a['packages_in_cycles']}",
                delta=a["packages_in_cycles"] - b["packages_in_cycles"])
    m[2].metric("Largest tangle", f"{b['largest_tangle']} → {a['largest_tangle']}",
                delta=a["largest_tangle"] - b["largest_tangle"])
    m[3].metric("Edges broken", len(gba.get("removed_edges", [])))
    removed = set(gba.get("removed_edges", []))
    focus = sorted({e.split("->")[0] for e in removed} | {e.split("->")[1] for e in removed})[:8]
    if not focus:
        st.caption("No edges were broken (nothing to visualize).")
        return
    c1, c2 = st.columns(2)
    with c1:
        st.caption("**Before** — red edges are the ones the refactorings break")
        st.iframe(_slice_graph_html(gba["before"]["edges"], focus, removed), height=400)
    with c2:
        st.caption("**After** — those edges are gone (cycles reduced)")
        st.iframe(_slice_graph_html(gba["after"]["edges"], focus, set()), height=400)

st.title("🚀 Analyze a Repository (end-to-end)")
st.caption("Paste a GitHub URL. DSARP clones it, detects architectural smells, suggests refactorings "
           "for every smell type, generates OpenRewrite recipes, applies them, and re-detects the "
           "smells to verify removal — showing the result at each step.")

from dsarp.verification.openrewrite_loop import available_detectors

_AVAIL = available_detectors()
_tools = [t for t, ok in _AVAIL.items() if ok]
st.caption("Real tools detected on this machine: " +
           (", ".join(f"**{t}**" for t in _tools) if _tools else "_none — install Arcan/Designite in tools/_"))

with st.form("analyze"):
    url = st.text_input("GitHub repository URL",
                        placeholder="https://github.com/apache/commons-validator")
    col = st.columns([2, 1])
    local = col[0].text_input("…or local path (optional)", placeholder="C:\\path\\to\\repo")
    top_k = col[1].number_input("Top-K suggestions", 3, 30, 8)
    real_loop = st.checkbox(
        "Also run the REAL tool loop (Arcan + Designite → OpenRewrite `mvn rewrite:run` → re-detect)",
        value=bool(_tools),
        help="Runs the actual tool binaries before and after a real source refactoring. "
             "Needs a Maven project that compiles; adds a few minutes.")
    detector = st.selectbox("Detector for the real loop", ["both", "arcan", "designite"],
                            index=0, disabled=not _tools)
    go = st.form_submit_button("▶️  Analyze", type="primary")

STEP_ICON = {"ok": "✅", "failed": "🔴"}

def _render_report(report: dict):
    if not report or not report.get("steps"):
        st.warning("No report to show yet.")
        return
    st.success(f"Analyzed **{report['project_id']}** (build system: {report.get('build_system')})")
    for s in report["steps"]:
        icon = STEP_ICON.get(s["status"], "•")
        with st.expander(f"{icon}  Step {s['step']} — {s['title']}  ·  _{s['tool']}_", expanded=True):
            st.write(s["summary"])
            d = s.get("detail", {})
            if "by_type" in d:
                st.bar_chart(d["by_type"])
            if "by_smell_type" in d:
                st.caption("Suggestions per smell type"); st.bar_chart(d["by_smell_type"])
            if d.get("top"):
                st.table([{"rank": t["rank"], "smell": t["smell"],
                           "refactoring": t["refactoring"], "score": round(t.get("score", 0), 2),
                           "components": t.get("components")} for t in d["top"]])
            if d.get("recipes"):
                st.caption("OpenRewrite recipes")
                st.table([{"refactoring": r["refactoring"], "recipe": r["recipe_type"],
                           "status": r["status"]} for r in d["recipes"]])
                if not d.get("maven_available", False):
                    st.info("Maven not installed → recipes are drafts; the change was applied by the "
                            "deterministic source transformer (equivalent to OpenRewrite's move/change).")
            if d.get("results"):
                st.caption("Per-suggestion effect")
                st.dataframe([{"refactoring": r["refactoring"], "method": r.get("method"),
                               "cycles before→after": f"{r.get('cycles_before')}→{r.get('cycles_after')}",
                               "removed": "✅" if r.get("smell_removed") else "—"}
                              for r in d["results"]], use_container_width=True, hide_index=True)
            if "packages_in_cycles_before" in d:
                cc = st.columns(3)
                cc[0].metric("Packages in cycles",
                             f"{d['packages_in_cycles_before']} → {d['packages_in_cycles_after']}")
                cc[1].metric("Freed", f"{d.get('packages_freed')} ({d.get('reduction_pct')}%)")
                cc[2].metric("Core tangle", f"{d['largest_tangle_before']} → {d['largest_tangle_after']}")
    _render_graph_before_after(report["project_id"])
    _render_real_loop(report["project_id"])


def _render_real_loop(project_id):
    """Smell counts measured by the REAL tools before and after `mvn rewrite:run`."""
    rep = read_json(data_dir() / "outputs" / project_id / "openrewrite_loop_report.json")
    if not rep:
        return
    st.divider()
    st.subheader(f"🔁 Real tool loop — {rep.get('tool', rep.get('detector'))}")
    st.caption("Smells measured by the actual tool binaries, before and after OpenRewrite "
               "rewrote the source. Not a simulation.")
    b, a = rep.get("smells_before"), rep.get("smells_after")
    if b is not None and a is not None:
        m = st.columns(4)
        m[0].metric("Smells before", b)
        m[1].metric("Smells after", a, delta=a - b)
        m[2].metric("Removed", b - a)
        m[3].metric("Files rewritten", len(rep.get("changed_files") or []))
    if rep.get("per_tool"):
        st.dataframe([{"tool": t, "before": v["before"], "after": v["after"],
                       "removed": v["removed"]} for t, v in rep["per_tool"].items()],
                     use_container_width=True, hide_index=True)
    b_by, a_by = rep.get("by_type_before") or {}, rep.get("by_type_after") or {}
    if b_by or a_by:
        types = sorted(set(b_by) | set(a_by))
        st.dataframe([{"smell type": t, "before": b_by.get(t, 0), "after": a_by.get(t, 0),
                       "delta": a_by.get(t, 0) - b_by.get(t, 0)} for t in types],
                     use_container_width=True, hide_index=True)
    st.page_link("pages/22_Real_Tool_Loop.py", label="Open the full step-by-step loop report →")


if go and (url or local):
    name = slug_to_dirname(url.split("github.com/")[-1].replace(".git", "")) if url else Path(local).name
    with st.spinner(f"Running the full pipeline on {name} … (large repos take a few minutes)"):
        from dsarp.e2e import run_pipeline
        report = run_pipeline(cfg(), name, repo_url=url or None,
                              repo_path=Path(local) if local else None, top_k=int(top_k))
    if real_loop and _tools:
        det = detector if _AVAIL.get(detector, False) or detector == "both" else _tools[0]
        with st.spinner(f"Real tool loop ({det}) — compiling, detecting, running OpenRewrite, "
                        "re-detecting … this takes a few minutes"):
            from dsarp.verification.openrewrite_loop import refactor_with_openrewrite_and_verify
            from dsarp.repositories.manager import RepositoryManager
            repo_path = Path(local) if local else RepositoryManager(data_dir()).path_for(name)
            sugs = read_json(data_dir() / "outputs" / name / "suggestions.json", default=[]) or []
            try:
                refactor_with_openrewrite_and_verify(cfg(), name, repo_path, sugs, detector=det)
            except Exception as e:  # keep the pipeline result visible even if the loop fails
                st.warning(f"Real tool loop could not complete: {e}")
    _render_report(report)
else:
    st.divider()
    st.subheader("Previous analyses")
    out = data_dir() / "outputs"
    prev = sorted([p.name for p in out.iterdir() if (p / "e2e_report.json").exists()]) if out.exists() else []
    if prev:
        pick = st.selectbox("Show a previous end-to-end report", prev)
        _render_report(read_json(out / pick / "e2e_report.json", default={}))
    else:
        st.info("No analyses yet. Paste a repo URL above and click Analyze.")
