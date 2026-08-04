"""Designite adapter (import mode).

Parses Designite CSV exports (ArchitectureSmells.csv / DesignSmells.csv style).
Column names are matched loosely so common Designite/DesigniteJava exports work.
Execute mode is stubbed: it records that a JVM run is required rather than faking output.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import List

from .base import EvidenceAdapter, ToolFinding


def _related_from_description(desc: str) -> List[str]:
    """Pull the peer components Designite names in its Description prose.

    Professional edition spells out the counterpart packages, e.g.
      "...depends on following less stable component(s): a.b.c; a.b"
      "...Following components realize the same concern: a.b; a.b.c."
    Those names are the tool's own evidence, so parsing them keeps the refactoring grounded
    instead of guessing which package the smell relates to.
    """
    if not desc or ":" not in desc:
        return []
    tail = desc.rsplit(":", 1)[1]
    out = []
    for part in re.split(r"[;,]", tail):
        name = part.strip().rstrip(".").strip()
        if re.fullmatch(r"[\w]+(\.[\w]+)+", name):
            out.append(name)
    return out


class DesigniteAdapter(EvidenceAdapter):
    name = "Designite"

    # "Code Smell" covers the free/community DesigniteJava designCodeSmells.csv
    # (columns: Project Name, Package Name, Type Name, Code Smell).
    _SMELL_COLS = ("Architecture Smell", "Design Smell", "Code Smell", "smell", "Smell")
    _COMP_COLS = ("Package Name", "Type Name", "Component", "Package", "Class")

    def import_findings(self, export_path: Path) -> List[ToolFinding]:
        export_path = Path(export_path)
        files: List[Path] = []
        if export_path.is_dir():
            files = list(export_path.glob("*.csv"))
        elif export_path.suffix.lower() == ".csv":
            files = [export_path]
        findings: List[ToolFinding] = []
        for f in files:
            findings.extend(self._parse_csv(f))
        return findings

    def _parse_csv(self, f: Path) -> List[ToolFinding]:
        out: List[ToolFinding] = []
        with open(f, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            headers = reader.fieldnames or []
            smell_col = self._pick(headers, self._SMELL_COLS)
            comp_col = self._pick(headers, self._COMP_COLS)
            # Designite Professional splits the component across columns: architecture smells
            # are Project,Package,Smell,Description; design/implementation smells add a Class
            # column. Join Package+Class into an FQN so downstream refactoring can locate it.
            pkg_col = self._pick(headers, ("Package Name", "Package"))
            cls_col = self._pick(headers, ("Type Name", "Class"))
            level = "class" if cls_col else "package"
            for row in reader:
                smell = (row.get(smell_col) or "").strip() if smell_col else ""
                comp = (row.get(comp_col) or "").strip() if comp_col else ""
                if cls_col and pkg_col:
                    pkg = (row.get(pkg_col) or "").strip()
                    cls = (row.get(cls_col) or "").strip()
                    if cls:
                        comp = f"{pkg}.{cls}" if pkg else cls
                if not smell or not comp:
                    continue
                related = _related_from_description(row.get("Description", ""))
                out.append(ToolFinding(
                    tool=self.name, smell_type=smell, component_level=level,
                    affected_components=[comp], severity=row.get("Severity", "medium") or "medium",
                    metrics={**{k: v for k, v in row.items()
                                if k not in (smell_col, comp_col) and v},
                             "related_components": related},
                    raw_ref=str(f),
                ).ensure_id())
        return out

    @staticmethod
    def _pick(headers, candidates):
        low = {h.lower(): h for h in headers}
        for c in candidates:
            if c.lower() in low:
                return low[c.lower()]
        return None

    def execute(self, repo_path: Path, revision: str, out_dir: Path,
                command: str = "", log_path: Path | None = None):
        """Run DesigniteJava if a command is configured; parse its CSV output.

        Returns ExecuteResult(findings, run). On missing binary / failure it emits
        NO findings (no fabrication) — the caller records status and marks evidence
        requires_source_inspection.
        """
        from .runner import ExecuteResult, run_command
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        run = run_command(command, cwd=repo_path, log_path=log_path,
                          env_subst={"repo_path": str(repo_path), "output_dir": str(out_dir)})
        run.output_dir = str(out_dir)
        findings = self.import_findings(out_dir) if run.status == "ok" else []
        return ExecuteResult(findings=findings, run=run)
