"""Tool adapter plugin interface.

Adapters read existing tool exports (import mode) or provide a shell command
template (execute mode). They emit raw smells/edges/metrics; the normalizer
turns those into EvidenceCase objects. Raw records are stored verbatim so raw
imports always stay separate from normalized evidence.
"""
from __future__ import annotations

import csv
import io
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Type


@dataclass
class RawSmell:
    tool: str
    tool_record_id: str
    raw_source_file: str
    smell_type_raw: str
    affected_components: list[str]
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawEdge:
    tool: str
    raw_source_file: str
    from_component: str
    to_component: str
    weight: float | None = None
    relation_type: str = "depends_on"
    confidence: float = 1.0


@dataclass
class RawMetric:
    tool: str
    raw_source_file: str
    component: str
    name: str
    value: Any


@dataclass
class AdapterResult:
    smells: list[RawSmell] = field(default_factory=list)
    edges: list[RawEdge] = field(default_factory=list)
    metrics: list[RawMetric] = field(default_factory=list)


class ToolAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def parse_import(self, path: Path) -> AdapterResult:
        """Parse an existing export file (CSV/JSON/TXT/XML/DOT)."""

    def build_command(self, tool_cfg: dict, project_path: str, output_dir: str) -> str:
        """Render the configured shell command for execute mode."""
        template = tool_cfg.get("command", "")
        if not template:
            raise ValueError(f"no command configured for tool '{self.name}'")
        params = {k: v for k, v in tool_cfg.items() if k != "command"}
        params.update({"project_path": project_path, "output_dir": output_dir})
        return template.format(**params)

    def output_files(self, output_dir: Path) -> list[Path]:
        """Files to import after an execute-mode run (default: all CSV/JSON)."""
        return sorted(list(output_dir.rglob("*.csv")) + list(output_dir.rglob("*.json")))


ADAPTERS: dict[str, Type[ToolAdapter]] = {}


def register_adapter(cls: Type[ToolAdapter]) -> Type[ToolAdapter]:
    ADAPTERS[cls.name] = cls
    return cls


def get_adapter(name: str) -> ToolAdapter:
    if name not in ADAPTERS:
        raise ValueError(f"unknown tool adapter '{name}'; available: {sorted(ADAPTERS)}")
    return ADAPTERS[name]()


# ---------------- shared parsing helpers ----------------

def read_csv_rows(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows = []
    for row in reader:
        rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items() if k})
    return rows


def pick(row: dict[str, str], *candidates: str) -> str:
    """Case/space/underscore-insensitive column lookup."""
    normalized = {k.lower().replace(" ", "").replace("_", "").replace("-", ""): v
                  for k, v in row.items()}
    for cand in candidates:
        key = cand.lower().replace(" ", "").replace("_", "").replace("-", "")
        if key in normalized and normalized[key] != "":
            return normalized[key]
    return ""


def split_components(value: str) -> list[str]:
    value = value.strip().strip("[]").strip()
    items: list[str] = [value] if value else []
    for sep in (";", "|", ","):
        if sep in value:
            items = value.split(sep)
            break
    out: list[str] = []
    for item in items:
        cleaned = item.strip().strip("'\"[]").strip()
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out
