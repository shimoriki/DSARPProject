import streamlit as st
from pathlib import Path
from _common import cfg, load_suggestions, load_report

st.title("🆕 Unseen Repository Evaluation")
st.caption("Add/point at ANY Java repo and generate evidence-grounded suggestions. "
           "Repository-independent — no hardcoded package names.")

c = cfg()
st.subheader("Register a local repository")
name = st.text_input("Project name", "my-project")
path = st.text_input("Local path to repo", "")
cola, colb = st.columns(2)
if cola.button("➕ Register") and name and path:
    from dsarp.repositories.manager import RepositoryManager
    RepositoryManager(c.data_dir).register_local(name, path)
    st.success(f"Registered {name} -> {path}")
if colb.button("▶️ Run inference (offline)") and name:
    from dsarp.inference.unseen import evaluate_unseen_repo
    from dsarp.repositories.manager import RepositoryManager
    from dsarp.export.report import build_report, write_report, write_suggestions
    repo_path = RepositoryManager(c.data_dir).path_for(name)
    with st.spinner("Preparing evidence + ranking ..."):
        sugs, report = evaluate_unseen_repo(c, name, repo_path=repo_path, top_k=3,
                                            model_override={"type": "offline"})
        out = c.data_dir / "outputs" / name
        write_suggestions(out / "suggestions.json", sugs)
        rep = build_report(name, "HEAD", sugs, report); rep["preparation"] = report.get("preparation")
        write_report(out / "report.json", rep)
    st.success(f"Generated {len(sugs)} suggestions for {name}")
    st.json(report.get("preparation", {}))

st.divider()
st.subheader("Results")
proj = st.text_input("Show results for project", name)
sugs = load_suggestions(proj)
rep = load_report(proj)
if rep.get("preparation"):
    prep = rep["preparation"]
    cc = st.columns(4)
    cc[0].metric("Build system", prep.get("build_system"))
    cc[1].metric("Source files", prep.get("source_files"))
    cc[2].metric("Graph source", prep.get("graph_source"))
    cc[3].metric("Smells", prep.get("smells"))
    st.caption(f"Tools used: {prep.get('tools_used')} · Unavailable: {prep.get('tools_unavailable')}")
for s in sugs[:10]:
    st.write(f"#{s['rank']} · {s['score']:.2f} · {s['smell_type']} → {s['recommended_refactoring']}")
