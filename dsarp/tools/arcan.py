"""Arcan adapter (import mode).

Parses Arcan smell exports. Real Arcan emits `smell-characteristics.csv` (one row per
smell instance: smellType, AffectedElements list, Severity, ATDI, ...) alongside
`smell-affects.csv` and `component-metrics.csv`. This adapter primarily reads
smell-characteristics.csv; it also accepts a normalized CSV or a JSON list.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import List

from ..util import read_json
from .base import EvidenceAdapter, ToolFinding

# Arcan smellType codes -> human-readable smell names
_ARCAN_SMELL = {
    "cyclicdep": "Cyclic Dependency",
    "hublikedep": "Hub-Like Dependency",
    "unstabledep": "Unstable Dependency",
    "godcomponent": "God Component",
    "godclass": "God Class",
}


def _severity_from(value: str) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "medium"
    return "high" if n >= 3 else "low" if n <= 1 else "medium"


def _severity_from_instability(value: str) -> str:
    """Martin instability (0..1): higher = more unstable = worse."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "medium"
    return "high" if n >= 0.8 else "low" if n < 0.5 else "medium"


# Arcan graphs the JDK/third-party nodes a project touches; those aren't ours to refactor.
_EXTERNAL_PREFIXES = ("java.", "javax.", "jdk.", "sun.", "com.sun.", "org.xml.sax",
                      "org.w3c.dom", "kotlin.", "scala.")


def _is_external(component: str) -> bool:
    return component.startswith(_EXTERNAL_PREFIXES)


def _parse_elements(cell: str) -> List[str]:
    """Parse Arcan AffectedElements like '[a.b.c, a.b, a]' -> ['a.b.c','a.b','a']."""
    if not cell:
        return []
    inner = cell.strip().strip("[]")
    return [p.strip() for p in re.split(r"[;,]", inner) if p.strip()]


class ArcanAdapter(EvidenceAdapter):
    name = "Arcan"

    def import_findings(self, export_path: Path) -> List[ToolFinding]:
        export_path = Path(export_path)
        if export_path.is_dir():
            # Prefer the canonical smell file; fall back to any csv/json.
            char = list(export_path.glob("smell-characteristics.csv"))
            if char:
                return self._parse_characteristics(char[0])
            # Arcan 1.2.1 (the runnable distribution) writes a different schema:
            # cycle membership matrices + UD/HL tables. Detect and parse that.
            if list(export_path.glob("*CyclicDependencyTable.csv")) or \
                    list(export_path.glob("UD*.csv")) or list(export_path.glob("HL*.csv")):
                return self.parse_arcan_1_2(export_path)
            findings: List[ToolFinding] = []
            for f in list(export_path.glob("*.csv")) + list(export_path.glob("*.json")):
                findings.extend(self.import_findings(f))
            return findings
        if export_path.suffix.lower() == ".json":
            return self._parse_json(export_path)
        if export_path.name == "smell-characteristics.csv":
            return self._parse_characteristics(export_path)
        if export_path.suffix.lower() == ".csv":
            return self._parse_csv(export_path)
        return []

    def _parse_characteristics(self, f: Path) -> List[ToolFinding]:
        out: List[ToolFinding] = []
        with open(f, "r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                code = (row.get("smellType") or "").strip().lower()
                comps = _parse_elements(row.get("AffectedElements", ""))
                if not code or not comps:
                    continue
                level = "package" if (row.get("AffectedConstructType", "")
                                      or "").upper().startswith("PACKAGE") else "class"
                out.append(ToolFinding(
                    tool=self.name,
                    smell_type=_ARCAN_SMELL.get(code, code),
                    component_level=level,
                    affected_components=comps,
                    severity=_severity_from(row.get("Severity", "")),
                    metrics={"ATDI": row.get("ATDI"), "size": row.get("Size"),
                             "strength": row.get("Strength"),
                             "central_component": row.get("CentralComponent")},
                    raw_ref=str(f),
                ).ensure_id())
        return out

    # ---- Arcan 1.2.1 output schema -------------------------------------------------
    # The runnable 1.2.1 distribution does NOT write smell-characteristics.csv. It writes:
    #   packageCyclicDependencyTable.csv / classCyclicDependencyTable.csv
    #       membership MATRIX: row = Cycle0..CycleN, column = component, cell 1 = member
    #   UD.csv / UD30.csv   unstable dependencies (package, instability, correlated package)
    #   HL.csv              hub-like dependencies (only written if any were detected)
    #   PM.csv / CM.csv     package / class metrics (not smells)

    def parse_arcan_1_2(self, out_dir: Path) -> List[ToolFinding]:
        out: List[ToolFinding] = []
        for name, level in (("packageCyclicDependencyTable.csv", "package"),
                            ("classCyclicDependencyTable.csv", "class")):
            f = out_dir / name
            if f.exists():
                out.extend(self._parse_cycle_matrix(f, level))
        for f in sorted(out_dir.glob("UD*.csv")):
            out.extend(self._parse_ud(f))
        for f in sorted(out_dir.glob("HL*.csv")):
            out.extend(self._parse_hl(f))
        return out

    def _parse_cycle_matrix(self, f: Path, level: str) -> List[ToolFinding]:
        """One finding per cycle row; members are the columns flagged 1."""
        out: List[ToolFinding] = []
        with open(f, "r", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader, None)
            if not header:
                return out
            components = header[1:]
            for row in reader:
                if not row:
                    continue
                members = [components[i] for i, cell in enumerate(row[1:])
                           if i < len(components) and (cell or "").strip() == "1"]
                # Ignore cycles made only of JDK/third-party nodes — not refactorable here.
                owned = [m for m in members if not _is_external(m)]
                if len(owned) < 2:
                    continue
                out.append(ToolFinding(
                    tool=self.name, smell_type="Cyclic Dependency", component_level=level,
                    affected_components=owned,
                    severity="high" if len(owned) >= 4 else "medium",
                    metrics={"cycle_id": row[0], "size": len(owned)},
                    raw_ref=str(f),
                ).ensure_id())
        return out

    def _parse_ud(self, f: Path) -> List[ToolFinding]:
        out: List[ToolFinding] = []
        with open(f, "r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                pkg = (row.get("UnstableDependenciesPackage") or "").strip()
                dep = (row.get("CorrelatedPackage") or "").strip()
                if not pkg:
                    continue
                out.append(ToolFinding(
                    tool=self.name, smell_type="Unstable Dependency",
                    component_level="package",
                    affected_components=[p for p in (pkg, dep) if p],
                    severity=_severity_from_instability(
                        row.get("InstabilityUnstableDependenciesPackage")),
                    metrics={"instability": row.get("InstabilityUnstableDependenciesPackage"),
                             "correlated_instability": row.get("InstabilityCorrelatedPackage")},
                    raw_ref=str(f),
                ).ensure_id())
        return out

    def _parse_hl(self, f: Path) -> List[ToolFinding]:
        out: List[ToolFinding] = []
        with open(f, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            headers = reader.fieldnames or []
            key = next((h for h in headers if "package" in h.lower() or "class" in h.lower()),
                       headers[0] if headers else None)
            if not key:
                return out
            for row in reader:
                comp = (row.get(key) or "").strip()
                if not comp:
                    continue
                out.append(ToolFinding(
                    tool=self.name, smell_type="Hub-Like Dependency",
                    component_level="class" if "class" in key.lower() else "package",
                    affected_components=[comp], severity="high",
                    metrics={k: v for k, v in row.items() if k != key and v},
                    raw_ref=str(f),
                ).ensure_id())
        return out

    def _parse_json(self, f: Path) -> List[ToolFinding]:
        data = read_json(f, default=[]) or []
        out: List[ToolFinding] = []
        for rec in data:
            comps = rec.get("affected_components") or rec.get("components") or []
            if isinstance(comps, str):
                comps = [comps]
            out.append(ToolFinding(
                tool=self.name,
                smell_type=rec.get("smell_type") or rec.get("type", "Cyclic Dependency"),
                component_level=rec.get("component_level", "package"),
                affected_components=comps,
                severity=str(rec.get("severity", "medium")),
                metrics=rec.get("metrics", {}),
                raw_ref=str(f),
            ).ensure_id())
        return out

    def _parse_csv(self, f: Path) -> List[ToolFinding]:
        out: List[ToolFinding] = []
        with open(f, "r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                comp = row.get("AffectedComponent") or row.get("Component") or row.get("Vertex")
                smell = row.get("SmellType") or row.get("Smell") or row.get("Type")
                if not comp or not smell:
                    continue
                out.append(ToolFinding(
                    tool=self.name, smell_type=smell.strip(),
                    component_level=row.get("Level", "package"),
                    affected_components=[comp.strip()],
                    severity=row.get("Severity", "medium") or "medium",
                    raw_ref=str(f),
                ).ensure_id())
        return out

    def execute(self, repo_path: Path, revision: str, out_dir: Path,
                command: str = "", log_path: Path | None = None):
        """Run Arcan if a command is configured; parse its output. No fabrication."""
        from .runner import ExecuteResult, run_command
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        run = run_command(command, cwd=repo_path, log_path=log_path,
                          env_subst={"repo_path": str(repo_path), "output_dir": str(out_dir)})
        run.output_dir = str(out_dir)
        findings = self.import_findings(out_dir) if run.status == "ok" else []
        return ExecuteResult(findings=findings, run=run)
