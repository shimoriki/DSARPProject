"""Loop 4 — tool evidence adapters (base interface).

Every architecture-smell tool (Arcan, Designite, …) implements EvidenceAdapter.
Two modes:
  - import mode  : parse a tool export the user already ran (default, laptop-safe)
  - execute mode : run the tool's JVM CLI (HPC; stubbed behind the same interface)
Adapters NEVER fabricate findings — missing evidence => empty list, not a guess.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Protocol

from ..util import evidence_id


@dataclass
class ToolFinding:
    tool: str
    smell_type: str
    component_level: str            # package | class | method
    affected_components: List[str]
    severity: str = "medium"
    metrics: Dict[str, Any] = field(default_factory=dict)
    evidence_id: str = ""
    raw_ref: str = ""               # pointer to raw record (kept out of prompts)

    def ensure_id(self) -> "ToolFinding":
        if not self.evidence_id:
            self.evidence_id = evidence_id(
                "EVID", self.tool, self.smell_type, *sorted(self.affected_components)
            )
        return self


class EvidenceAdapter(Protocol):
    name: str

    def import_findings(self, export_path: Path) -> List[ToolFinding]: ...

    def execute(self, repo_path: Path, revision: str, out_dir: Path) -> List[ToolFinding]: ...
