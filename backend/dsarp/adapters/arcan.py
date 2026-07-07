"""Arcan adapter: parses architectural-smell and dependency-edge exports.

Arcan CSV column names vary between versions, so lookups are synonym-based.
Files whose headers look like an edge list (source/target, from/to) are
imported as dependency edges; anything else is treated as smell records.
"""
from __future__ import annotations

import json
from pathlib import Path

from .base import (AdapterResult, RawEdge, RawMetric, RawSmell, ToolAdapter,
                   pick, read_csv_rows, register_adapter, split_components)

_EDGE_FROM = ("source", "from", "fromcomponent", "src", "dependencyfrom", "vertexfrom")
_EDGE_TO = ("target", "to", "tocomponent", "dst", "dependencyto", "vertexto")
_SMELL_ID = ("id", "smellid", "vertexid", "uniquesmellid", "arcanid")
_SMELL_TYPE = ("smelltype", "smell", "smellname")
_AFFECTED = ("affectedelements", "affectedcomponents", "elements", "components",
             "belongstocomponents", "affected", "cycle")
# component-metrics style files: one row per component, numeric quality metrics
_METRIC_COMPONENT = ("name", "componentname", "component", "packagename")
_METRIC_COLUMNS = ("FanIn", "FanOut", "InstabilityMetric", "AbstractnessMetric",
                   "LinesOfCode", "PageRank")


@register_adapter
class ArcanAdapter(ToolAdapter):
    name = "arcan"

    def parse_import(self, path: Path) -> AdapterResult:
        suffix = path.suffix.lower()
        if suffix == ".json":
            return self._parse_json(path)
        if suffix in (".csv", ".txt", ".tsv"):
            return self._parse_csv(path)
        raise ValueError(f"ArcanAdapter cannot parse '{path.name}' "
                         f"(expected .csv/.tsv/.txt/.json)")

    def _parse_csv(self, path: Path) -> AdapterResult:
        rows = read_csv_rows(path)
        result = AdapterResult()
        if not rows:
            return result
        if not pick(rows[0], *_SMELL_TYPE) and pick(rows[0], *_METRIC_COMPONENT) \
                and any(pick(rows[0], m) for m in _METRIC_COLUMNS):
            for row in rows:
                component = pick(row, *_METRIC_COMPONENT)
                if not component:
                    continue
                for metric in _METRIC_COLUMNS:
                    value = pick(row, metric)
                    if value != "":
                        result.metrics.append(RawMetric(
                            tool=self.name, raw_source_file=path.name,
                            component=component, name=metric, value=value))
            return result
        if pick(rows[0], *_EDGE_FROM) and pick(rows[0], *_EDGE_TO):
            for row in rows:
                frm, to = pick(row, *_EDGE_FROM), pick(row, *_EDGE_TO)
                if not frm or not to:
                    continue
                weight_s = pick(row, "weight", "count", "numdependencies", "strength")
                result.edges.append(RawEdge(
                    tool=self.name, raw_source_file=path.name,
                    from_component=frm, to_component=to,
                    weight=float(weight_s) if weight_s else None))
            return result
        for i, row in enumerate(rows):
            smell_type = pick(row, *_SMELL_TYPE)
            if not smell_type:
                continue
            affected = split_components(pick(row, *_AFFECTED))
            record_id = pick(row, *_SMELL_ID) or f"row{i + 1}"
            known = {"severity": pick(row, "severity", "severitylevel"),
                     "cycle_size": pick(row, "size", "cyclesize", "numelements"),
                     "atdi": pick(row, "atdi", "techdebtindex", "severityscore")}
            attributes = {k: v for k, v in known.items() if v}
            attributes.update({k: v for k, v in row.items() if v})
            result.smells.append(RawSmell(
                tool=self.name, tool_record_id=record_id, raw_source_file=path.name,
                smell_type_raw=smell_type, affected_components=affected,
                attributes=attributes))
        return result

    def _parse_json(self, path: Path) -> AdapterResult:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        records = data if isinstance(data, list) else data.get("smells", [])
        result = AdapterResult()
        for i, rec in enumerate(records):
            if not isinstance(rec, dict):
                continue
            smell_type = str(rec.get("smellType") or rec.get("type") or rec.get("smell_type") or "")
            if not smell_type:
                continue
            affected = rec.get("affectedElements") or rec.get("affected_components") or []
            if isinstance(affected, str):
                affected = split_components(affected)
            result.smells.append(RawSmell(
                tool=self.name,
                tool_record_id=str(rec.get("id", f"json{i + 1}")),
                raw_source_file=path.name, smell_type_raw=smell_type,
                affected_components=[str(a) for a in affected],
                attributes={k: v for k, v in rec.items()
                            if k not in ("affectedElements", "affected_components")}))
        edges = data.get("edges", []) if isinstance(data, dict) else []
        for e in edges:
            if isinstance(e, dict) and e.get("from") and e.get("to"):
                result.edges.append(RawEdge(
                    tool=self.name, raw_source_file=path.name,
                    from_component=str(e["from"]), to_component=str(e["to"]),
                    weight=e.get("weight")))
        return result
