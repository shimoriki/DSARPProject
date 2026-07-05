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
    r"(?:with|between|involving|among)\s*:?\s*(?P<list>[\w.$\-, ;]+)", re.IGNORECASE)


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
            cause = pick(row, "causeofthesmell", "cause", "description", "details")
            affected = [component]
            m = _PARTICIPANTS_RE.search(cause)
            if m:
                for part in split_components(m.group("list")):
                    cleaned = part.strip().rstrip(".")
                    if cleaned and cleaned not in affected:
                        affected.append(cleaned)
            attributes = {"cause": cause} if cause else {}
            attributes.update({k: v for k, v in row.items() if v})
            result.smells.append(RawSmell(
                tool=self.name, tool_record_id=f"row{i + 1}",
                raw_source_file=path.name, smell_type_raw=smell_type,
                affected_components=affected, attributes=attributes))
        return result
