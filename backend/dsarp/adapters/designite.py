"""Designite / DesigniteJava adapter for architecture & design smell CSVs.

Typical columns: "Project Name", "Package Name", "Architecture Smell",
"Cause of the Smell". For cycles Designite lists each participating package
on its own row; participants named in the cause text are folded into
affected_components so the normalizer can merge rows into one case.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import (AdapterResult, RawSmell, ToolAdapter, pick, read_csv_rows,
                   register_adapter, split_components)

_PARTICIPANTS_RE = re.compile(
    r"(?:cycles?\s+are|with|between|involving|among)\s*:?\s*(?P<list>[\w.$\-, ;]+)",
    re.IGNORECASE)


def _looks_like_component(token: str) -> bool:
    return bool(token) and not token.isdigit() and ("." in token or len(token) > 2)


@register_adapter
class DesigniteAdapter(ToolAdapter):
    name = "designite"

    def parse_import(self, path: Path) -> AdapterResult:
        if path.suffix.lower() not in (".csv", ".txt", ".tsv"):
            raise ValueError(f"DesigniteAdapter cannot parse '{path.name}' (expected CSV)")
        rows = read_csv_rows(path)
        result = AdapterResult()
        for i, row in enumerate(rows):
            smell_type = pick(row, "architecturesmell", "designsmell",
                              "implementationsmell", "smell", "smellname")
            component = pick(row, "packagename", "package", "componentname",
                             "component", "namespace", "typename", "classname")
            if not smell_type or not component:
                continue
            cls = pick(row, "class", "classname", "typename")
            method = pick(row, "method", "methodname")
            if cls:  # class/method-level smells target the concrete element
                component = f"{component}.{cls}" + (f"::{method}" if method else "")
            cause = pick(row, "causeofthesmell", "cause", "description", "details")
            affected = [component]
            # participant lists are only meaningful for dependency-cycle smells;
            # elsewhere "are: 54" style counts would pollute the component list
            if "cycl" in smell_type.lower():
                m = _PARTICIPANTS_RE.search(cause)
                if m:
                    for part in split_components(m.group("list")):
                        cleaned = part.strip().rstrip(".")
                        if _looks_like_component(cleaned) and cleaned not in affected:
                            affected.append(cleaned)
            attributes = {"cause": cause} if cause else {}
            attributes.update({k: v for k, v in row.items() if v})
            result.smells.append(RawSmell(
                tool=self.name, tool_record_id=f"row{i + 1}",
                raw_source_file=path.name, smell_type_raw=smell_type,
                affected_components=affected, attributes=attributes))
        return result
