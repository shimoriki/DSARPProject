"""Import existing file outputs (data/outputs/*, normalized/*, graphs/*) into SQLite.

Used by `dsarp-local db import-outputs`. File outputs remain the source of truth;
this just indexes them for cross-session querying.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ..util import read_json, read_jsonl
from .repositories import Store


def import_outputs(data_dir: Path, store: Store) -> Dict[str, int]:
    data_dir = Path(data_dir)
    counts = {"projects": 0, "suggestions": 0, "reports": 0, "hgrs": 0, "graphs": 0}

    # normalized evidence cases -> repositories + evidence_cases
    for case_file in (data_dir / "normalized").glob("*.json"):
        case = read_json(case_file)
        if not case:
            continue
        store.save_repository(project_id=case["project_id"], revision=case.get("revision", ""))
        store.save_evidence_case(case)
        counts["projects"] += 1

    # graphs
    for gfile in (data_dir / "graphs").glob("*.json"):
        g = read_json(gfile) or {}
        gm = g.get("graph_metrics", {})
        store.save_graph_metadata(gfile.stem, "HEAD", "", gm)
        counts["graphs"] += 1

    # per-project outputs
    out = data_dir / "outputs"
    if out.exists():
        for proj_dir in out.iterdir():
            if not proj_dir.is_dir():
                continue
            pid = proj_dir.name
            sugs = read_json(proj_dir / "suggestions.json", default=[]) or []
            if sugs:
                counts["suggestions"] += store.save_suggestions(sugs)
            report = read_json(proj_dir / "report.json")
            if report:
                store.save_token_report(report.get("token_optimisation", {}) | {"project_id": pid})
                counts["reports"] += 1
            for rev in read_jsonl(proj_dir / "hgrs_reviews.jsonl"):
                store.save_hgrs(rev, project_id=pid)
                counts["hgrs"] += 1
    return counts
