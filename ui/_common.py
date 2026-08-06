"""Shared helpers for the Streamlit human-analysis interface (read-only over data/)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dsarp.config import load_config  # noqa: E402
from dsarp.util import read_json  # noqa: E402


def cfg():
    return load_config("local")


def data_dir() -> Path:
    return cfg().data_dir


def list_projects() -> List[str]:
    norm = data_dir() / "normalized"
    if not norm.exists():
        return []
    return sorted(p.stem for p in norm.glob("*.json"))


def load_case(project_id: str) -> Any:
    return read_json(data_dir() / "normalized" / f"{project_id}.json", default=None)


def load_suggestions(project_id: str) -> list:
    return read_json(data_dir() / "outputs" / project_id / "suggestions.json", default=[]) or []


def load_report(project_id: str) -> dict:
    return read_json(data_dir() / "outputs" / project_id / "report.json", default={}) or {}


def load_graph(project_id: str) -> dict:
    return read_json(data_dir() / "graphs" / f"{project_id}.json", default={}) or {}


# The dashboard opened on whatever sorted first, which is apache-cassandra - an ANT project
# DSARP cannot refactor at all, so every page led with an empty or "unsupported build"
# result. commons-validator is the repository with the strongest verified result (76 -> 62,
# reproduced across three runs), so it is the sensible thing to land on.
DEFAULT_PROJECT_HINTS = ("commons-validator", "pdfbox", "commons-io")


def default_index(options) -> int:
    """Index of the best repository to show first, or 0 when none of them are present."""
    opts = list(options or [])
    for hint in DEFAULT_PROJECT_HINTS:
        for i, name in enumerate(opts):
            if hint in str(name):
                return i
    return 0
