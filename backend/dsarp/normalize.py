"""Evidence Normalizer: raw tool findings -> merged, provenance-rich cases.

Rules enforced here:
- Raw imports stay untouched in raw_findings; normalization is re-runnable.
- Findings from different tools describing the same smell (same canonical
  category + same component set) merge into one case with multiple findings.
- Dependency evidence is attached only when both endpoints belong to the
  case's affected components; nothing is inferred.
- Missing direction knowledge is recorded explicitly as a limitation.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .config import AppConfig
from .log import get_logger
from .models.evidence import (DependencyEvidence, EvidenceCase, MetricEvidence,
                              ToolFinding)
from .registry import canonical_smell
from .store.repos import Store

log = get_logger("normalize")

EVIDENCE_VERSION = "ev1"


def _case_id(project_id: str, smell_key: str, components: list[str]) -> str:
    basis = f"{project_id}|{smell_key}|{'|'.join(sorted(components))}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def build_evidence(store: Store, cfg: AppConfig, project_name: str) -> list[EvidenceCase]:
    project = store.get_project(project_name)
    if not project:
        raise ValueError(f"unknown project '{project_name}'")
    pid = project["id"]

    smell_records = store.raw_findings_for_project(pid, kind="smell")
    edge_rows = store.edges_for_project(pid)

    # Group raw smell findings by (canonical key, frozen component set)
    groups: dict[tuple[str, frozenset], list[dict]] = {}
    for rec in smell_records:
        record = json.loads(rec["record_json"])
        components = record.get("affected_components", [])
        if not components:
            continue
        key, _display, _code = canonical_smell(record.get("smell_type_raw", ""))
        groups.setdefault((key, frozenset(components)), []).append(
            {**record, "tool": rec["tool"], "canonical_key": key})

    # Deterministic ordering -> stable smell ids across rebuilds
    ordered = sorted(groups.items(), key=lambda kv: (kv[0][0], sorted(kv[0][1])))
    seq_by_code: dict[str, int] = {}
    cases: list[EvidenceCase] = []

    for (key, comp_set), records in ordered:
        _k, display, code = canonical_smell(records[0].get("smell_type_raw", key))
        seq_by_code[code] = seq_by_code.get(code, 0) + 1
        primary_tool = records[0]["tool"].upper()
        smell_id = f"{primary_tool}_{code}_{seq_by_code[code]:03d}"
        components = sorted(comp_set)

        findings = []
        for n, r in enumerate(records, start=1):
            findings.append(ToolFinding(
                tool=r["tool"],
                tool_record_id=str(r.get("tool_record_id", "")),
                evidence_id=f"{r['tool'].upper()}_{code}_{seq_by_code[code]:03d}"
                            + (f"_{n}" if n > 1 else ""),
                raw_source_file=r.get("raw_source_file", ""),
                attributes=_clean_attributes(r.get("attributes", {}))))

        deps = []
        comp_lookup = set(components)
        for e in edge_rows:
            if e["from_component"] in comp_lookup and e["to_component"] in comp_lookup:
                deps.append(DependencyEvidence(
                    **{"from": e["from_component"], "to": e["to_component"]},
                    relation_type=e["relation_type"], evidence_id=e["evidence_id"],
                    confidence=e["confidence"], source=e["source"]))

        limitations = []
        covered = {(d.from_component, d.to_component) for d in deps}
        if key == "cyclic_dependency":
            uncovered = [(a, b) for a in components for b in components
                         if a != b and (a, b) not in covered and (b, a) not in covered]
            if uncovered and len(components) > 1:
                pairs = ", ".join(f"{a} <-> {b}" for a, b in uncovered[:5])
                limitations.append(
                    "Exact source-level dependency direction is unavailable for: "
                    f"{pairs}. Requires source inspection.")
        if not deps:
            limitations.append(
                "No dependency edge evidence was imported for this case; "
                "all edge directions require source inspection.")

        metrics = []
        for f in findings:
            for mname in ("atdi", "cycle_size", "severity"):
                if mname in f.attributes and f.attributes[mname] not in ("", None):
                    metrics.append(MetricEvidence(
                        evidence_id=f"{f.evidence_id}_M_{mname.upper()}",
                        component="", name=mname, value=f.attributes[mname],
                        tool=f.tool))

        case = EvidenceCase(
            case_id=_case_id(pid, key, components),
            project_id=project["name"],
            source_revision=project.get("source_revision"),
            architecture_type=project.get("architecture_type", "package-based-java"),
            component_type=project.get("component_type", "package"),
            smell_id=smell_id,
            smell_type=display,
            smell_key=key,
            affected_components=components,
            tool_findings=findings,
            dependency_evidence=deps,
            metrics=metrics,
            limitations=limitations)
        store.upsert_case(case)
        cases.append(case)

    store.audit("evidence", project["name"], "build",
                details={"cases": len(cases), "evidence_version": EVIDENCE_VERSION})
    log.info("built %d evidence cases for project %s", len(cases), project["name"])
    return cases


def _clean_attributes(attrs: dict[str, Any]) -> dict[str, Any]:
    cleaned = {}
    for k, v in attrs.items():
        if v in ("", None):
            continue
        key = str(k).strip().lower().replace(" ", "_")
        if key in ("kind", "raw_source_file", "tool_record_id", "smell_type_raw",
                   "affected_components", "tool"):
            continue
        cleaned[key] = v
    return cleaned
