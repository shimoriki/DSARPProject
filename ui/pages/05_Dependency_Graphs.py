import streamlit as st
from _common import list_projects, load_graph, default_index

st.title("🕸️ Dependency Graphs")
st.caption("Loop 5: package graph, cycles, SCCs, central components (fan-in/out).")

projects = list_projects()
sel = st.selectbox("Project", projects or ["(none)"],
                   index=default_index(projects or ["(none)"]))
g = load_graph(sel)
gm = g.get("graph_metrics", {})
c = st.columns(4)
c[0].metric("Nodes", gm.get("node_count", 0))
c[1].metric("Edges", gm.get("edge_count", 0))
c[2].metric("Cycles", gm.get("cycle_count", 0))
c[3].metric("SCCs", gm.get("scc_count", 0))

nodes = g.get("nodes", [])
if nodes:
    st.subheader("Central components (by fan-in + fan-out)")
    ranked = sorted(nodes, key=lambda n: n["metrics"].get("fan_in", 0)
                    + n["metrics"].get("fan_out", 0), reverse=True)[:15]
    st.table([{"component": n["id"], **n["metrics"]} for n in ranked])

if gm.get("cycles"):
    st.subheader("Cycles")
    for cyc in gm["cycles"][:20]:
        st.write(" → ".join(cyc) + " → " + cyc[0])

# Optional interactive graph
try:
    import base64
    import networkx as nx
    from pyvis.network import Network
    if st.checkbox("Render interactive graph (pyvis)") and g.get("edges"):
        net = Network(height="500px", directed=True, bgcolor="#ffffff")
        for n in nodes:
            net.add_node(n["id"], label=n["id"].split(".")[-1])
        for e in g["edges"]:
            net.add_edge(e["source"], e["target"], value=e.get("weight", 1))
        # st.components.v1.html is deprecated (removed after 2026-06-01); embed the
        # self-contained pyvis document via st.iframe using a base64 data URI.
        html = net.generate_html(notebook=False)
        data_uri = "data:text/html;base64," + base64.b64encode(html.encode("utf-8")).decode()
        st.iframe(data_uri, height=540)
except Exception as exc:
    st.caption(f"Interactive graph needs pyvis (`pip install pyvis`). {exc}")
