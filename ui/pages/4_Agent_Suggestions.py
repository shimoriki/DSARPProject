import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _bootstrap import get_ctx, project_selector  # noqa: E402
from dsarp import services  # noqa: E402

st.set_page_config(page_title="Agent Suggestions", layout="wide")
ctx = get_ctx()
st.title("4 · Agent Suggestions")

pname = project_selector(ctx)
if pname:
    cases = ctx.store.list_cases(project_id=pname)
    st.subheader("Run agents")
    with st.form("run_agents"):
        mode = st.selectbox("Agent mode", ["baseline", "skill", "tool_evidence"], index=2)
        provider = st.selectbox(
            "Provider", ["(configured default)", "ollama", "openai_compat",
                         "llamacpp", "hf_endpoint", "mock"])
        model_id = st.text_input("Model id (blank = configured default)",
                                 placeholder=ctx.cfg.model.model_id)
        selected = st.multiselect(
            "Cases (blank = all)", [c["id"] for c in cases],
            format_func=lambda cid: next(
                f"{c['smell_id']} · {c['smell_type']}" for c in cases if c["id"] == cid))
        use_critic = st.checkbox("Also run critic agent for suggested scores",
                                 value=ctx.cfg.critic.enabled)
        if st.form_submit_button("Run"):
            try:
                with st.spinner("Calling local model..."):
                    runs = services.run_agents(
                        ctx, pname, mode,
                        case_ids=selected or None,
                        provider_name=None if provider.startswith("(") else provider,
                        model_id=model_id or None,
                        with_critic=use_critic or None)
                ok = sum(1 for r in runs if r["status"] == "ok")
                st.success(f"{ok}/{len(runs)} runs valid JSON.")
            except Exception as exc:
                st.error(str(exc))

    st.subheader("Runs")
    runs = ctx.store.list_runs(project_id=pname)
    if runs:
        st.dataframe(
            [{k: r[k] for k in ("run_id", "smell_id", "agent_mode", "model_id",
                                "skill_version", "prompt_version", "status",
                                "total_tokens", "runtime_seconds", "created_at")}
             for r in runs], use_container_width=True)
        run_id = st.selectbox("Inspect run", [r["run_id"] for r in runs])
        run = ctx.store.get_run(run_id)
        if run["status"] == "ok":
            st.json(json.loads(run["suggestion_json"]))
            checks = json.loads(run.get("structural_checks_json") or "{}")
            with st.expander("Automatic structural checks"):
                for c in checks.get("checks", []):
                    icon = "✅" if c["passed"] else "❌"
                    st.text(f"{icon} {c['name']}: {c['detail']}")
        else:
            st.error(f"status = {run['status']}: {run.get('error')}")
            if run.get("raw_response"):
                with st.expander("Raw model response (stored verbatim)"):
                    st.code(run["raw_response"])
    else:
        st.info("No runs yet.")
