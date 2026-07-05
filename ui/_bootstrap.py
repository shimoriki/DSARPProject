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
