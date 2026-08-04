"""Loops 2-3 — commit mining + RefactoringMiner extraction (import mode).

RefactoringMiner emits JSON of the form {"commits": [{"sha1", "refactorings": [...]}]}.
This adapter imports that JSON into normalized RefactoringEvent records.
Execute mode (running the RefactoringMiner CLI/jar per commit) is stubbed behind
the same interface for the HPC batch path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from ..util import evidence_id, read_json


# STRICTLY architectural refactorings — change module/package/class structure or
# inter-component coupling/hierarchy. Code-level refactorings (Extract Method, Rename
# Method/Variable, Change Access/Modifier, Extract Variable, Inline, ...) are EXCLUDED
# on purpose: we train only on architectural evidence.
ARCHITECTURAL_REFACTORINGS = {
    # class/type relocation & extraction
    "Move Class", "Move And Rename Class", "Rename Class",
    "Extract Class", "Extract Subclass", "Extract Superclass", "Extract Interface",
    # method relocation across types (changes coupling) — NOT plain Extract Method
    "Move Method", "Move And Rename Method", "Extract And Move Method",
    "Pull Up Method", "Push Down Method",
    # field/attribute relocation across types/hierarchy
    "Move Attribute", "Move And Rename Attribute",
    "Pull Up Attribute", "Push Down Attribute",
    # package-level
    "Split Package", "Merge Package", "Move Package", "Rename Package",
    "Change Package",
}


def is_architectural(refactoring_type: str) -> bool:
    return refactoring_type in ARCHITECTURAL_REFACTORINGS


@dataclass
class RefactoringEvent:
    event_id: str
    commit_sha: str
    refactoring_type: str
    before_entity: str = ""
    after_entity: str = ""
    file_paths: List[str] = field(default_factory=list)
    description: str = ""
    affected_components: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__


class RefactoringMinerAdapter:
    name = "RefactoringMiner"

    def import_events(self, export_path: Path) -> List[RefactoringEvent]:
        data = read_json(Path(export_path), default={}) or {}
        commits = data.get("commits", data if isinstance(data, list) else [])
        events: List[RefactoringEvent] = []
        for commit in commits:
            sha = commit.get("sha1") or commit.get("sha") or commit.get("commit", "")
            for r in commit.get("refactorings", []):
                events.append(self._to_event(sha, r))
        return events

    def _to_event(self, sha: str, r: Dict[str, Any]) -> RefactoringEvent:
        rtype = r.get("type", "Other")
        desc = r.get("description", "")
        left = r.get("leftSideLocations", []) or []
        right = r.get("rightSideLocations", []) or []
        files = sorted({loc.get("filePath", "") for loc in (left + right) if loc.get("filePath")})
        before = left[0].get("codeElement", "") if left else ""
        after = right[0].get("codeElement", "") if right else ""
        comps = sorted({self._pkg_of(f) for f in files if f})
        return RefactoringEvent(
            event_id=evidence_id("REF", sha, rtype, desc[:40]),
            commit_sha=sha, refactoring_type=rtype,
            before_entity=before, after_entity=after,
            file_paths=files, description=desc, affected_components=comps,
        )

    @staticmethod
    def _pkg_of(file_path: str) -> str:
        # src/main/java/org/apache/x/Y.java -> org.apache.x
        parts = file_path.replace("\\", "/").split("/")
        if "java" in parts:
            parts = parts[parts.index("java") + 1:]
        pkg = ".".join(parts[:-1])
        return pkg or file_path

    def execute(self, repo_path: Path, out_dir: Path, executable: str = "",
                commit: str = "", commit_range: tuple = (), limit: int = 0,
                log_path: Path | None = None):
        """Run RefactoringMiner and import its JSON. No fabrication on failure.

        Modes (mutually exclusive, checked in order):
          commit         -> `-c <repo> <sha>`
          commit_range   -> `-bc <repo> <startSha> <endSha>`
          limit>0        -> `-a <repo> <branch>` capped downstream
        Returns ExecuteResult(events, run).
        """
        from ..tools.runner import ExecuteResult, run_command
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_json = out_dir / "refactoringminer.json"
        if not executable:
            return ExecuteResult(findings=[], run=run_command("", log_path=log_path))
        if commit:
            cmd = f'{executable} -c "{repo_path}" {commit} -json "{out_json}"'
        elif commit_range and len(commit_range) == 2:
            cmd = f'{executable} -bc "{repo_path}" {commit_range[0]} {commit_range[1]} -json "{out_json}"'
        else:
            cmd = f'{executable} -a "{repo_path}" -json "{out_json}"'
        run = run_command(cmd, cwd=repo_path, log_path=log_path)
        run.output_dir = str(out_dir)
        events = self.import_events(out_json) if run.status == "ok" and out_json.exists() else []
        if limit and events:
            events = events[:limit]
        return ExecuteResult(findings=events, run=run)
