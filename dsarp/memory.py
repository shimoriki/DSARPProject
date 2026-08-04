"""Project memory (Level 1 context) — compact per-repo summaries.

Regenerated only when repo revision / tool / graph hashes change. Future runs
read these first instead of raw logs (token policy).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .util import read_json, write_json

MEMORY_FILES = [
    "project_summary.md",
    "architecture_summary.json",
    "tool_summary.json",
    "graph_summary.json",
    "refactoring_history_summary.json",
    "openrewrite_capability_summary.json",
]


class ProjectMemory:
    def __init__(self, data_dir: Path, project_id: str):
        self.dir = Path(data_dir) / "memory" / project_id
        self.project_id = project_id

    def path(self, name: str) -> Path:
        return self.dir / name

    def read_json(self, name: str, default: Any = None) -> Any:
        return read_json(self.path(name), default=default)

    def write_json(self, name: str, obj: Any) -> None:
        write_json(self.path(name), obj)

    def write_text(self, name: str, text: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.path(name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def memory_ref(self, revision: str) -> str:
        return f"PROJECT_SUMMARY_{self.project_id}_{revision[:8]}"

    def compact_summary(self) -> Dict[str, Any]:
        """Level-1 project summary bundle for context packages (small)."""
        return {
            "project_id": self.project_id,
            "architecture": self.read_json("architecture_summary.json", {}),
            "graph": self.read_json("graph_summary.json", {}),
            "tools": self.read_json("tool_summary.json", {}),
            "openrewrite_capability": self.read_json("openrewrite_capability_summary.json", {}),
        }
