"""Shared setup for all Streamlit pages: sys.path + cached AppContext."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from dsarp import services  # noqa: E402


@st.cache_resource
def get_ctx() -> "services.AppContext":
    return services.init_context(root_dir=ROOT)


def project_selector(ctx, key: str = "project"):
    projects = ctx.store.list_projects()
    if not projects:
        st.warning("No projects yet — add one on the Projects page.")
        return None
    names = [p["name"] for p in projects]
    return st.selectbox("Project", names, key=key)


SUGGESTED_LABEL = "Suggested system value — requires human confirmation"


def evidence_backed_banner(checks: dict) -> None:
    """Tell the reviewer plainly whether a suggestion is evidence-backed."""
    if not checks:
        st.warning("⚠️ No structural checks recorded for this run — treat every "
                   "claim as unverified.")
        return
    if checks.get("critical_hallucination"):
        problems = []
        if checks.get("unsupported_evidence_ids"):
            problems.append(f"cites unknown evidence IDs "
                            f"{checks['unsupported_evidence_ids']}")
        if checks.get("ungrounded_components"):
            problems.append(f"names components absent from the evidence "
                            f"{checks['ungrounded_components']}")
        failed = [c["name"] for c in checks.get("checks", []) if not c["passed"]]
        if "edge_direction_claim_supported" in failed:
            problems.append("claims a dependency direction no imported edge supports")
        st.error("🚫 NOT evidence-backed — this suggestion " +
                 "; ".join(problems or ["failed grounding checks"]) +
                 ". Verify against the source code before acting on it.")
    else:
        st.success("✅ Evidence-backed — every cited evidence ID, component, and "
                   "claimed dependency direction was verified against the imported "
                   "tool data. Anything the evidence cannot support is marked "
                   "'Requires source inspection.'")
