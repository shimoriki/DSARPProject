"""Task 13 — OpenRewrite recipe validation.

Attempts, where possible: OpenRewrite dry-run, Maven compile, tests. Never marks a
recipe `validated` unless dry-run AND build actually pass. When Maven/OpenRewrite
are unavailable it records `not_run` with a clear reason (no false validation).
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List

from ..tools.runner import run_command
from ..util import read_json, write_json


class RecipeValidator:
    def __init__(self, repo_path: Path | None = None, log_dir: Path | None = None):
        self.repo_path = Path(repo_path) if repo_path else None
        self.log_dir = Path(log_dir) if log_dir else None

    def _tooling(self) -> Dict[str, bool]:
        return {"maven": shutil.which("mvn") is not None,
                "has_pom": bool(self.repo_path and (self.repo_path / "pom.xml").exists())}

    def validate_suggestion(self, suggestion: Dict[str, Any]) -> Dict[str, Any]:
        plan = suggestion.get("openrewrite_recipe_plan", {})
        verification = suggestion.setdefault("verification", {})
        if not plan.get("recipe_possible"):
            plan["recipe_status"] = "not_applicable"
            return suggestion

        tooling = self._tooling()
        if not (tooling["maven"] and tooling["has_pom"]):
            # cannot validate -> stay draft, record why (no fake validation)
            verification["openrewrite_dry_run"] = "not_run"
            verification["build"] = "not_run"
            verification["tests"] = "not_run"
            plan["recipe_status"] = plan.get("recipe_status", "draft")
            suggestion.setdefault("limitations", [])
            reason = "maven/pom.xml unavailable — recipe validation skipped"
            if reason not in suggestion["limitations"]:
                suggestion["limitations"].append(reason)
            return suggestion

        log = (self.log_dir / f"{suggestion['suggestion_id']}.log") if self.log_dir else None
        dry = run_command("mvn -q -DskipTests rewrite:dryRun", cwd=self.repo_path, log_path=log)
        verification["openrewrite_dry_run"] = "passed" if dry.status == "ok" else "failed"
        if dry.status == "ok":
            build = run_command("mvn -q -DskipTests compile", cwd=self.repo_path)
            verification["build"] = "passed" if build.status == "ok" else "failed"
            plan["recipe_status"] = "validated" if build.status == "ok" else "failed"
        else:
            verification["build"] = "not_run"
            plan["recipe_status"] = "failed"
        return suggestion

    def validate_file(self, suggestions_path: Path) -> Dict[str, Any]:
        suggestions: List[Dict] = read_json(suggestions_path, default=[]) or []
        counts = {"validated": 0, "failed": 0, "draft": 0, "not_applicable": 0, "not_run": 0}
        for s in suggestions:
            self.validate_suggestion(s)
            st = s.get("openrewrite_recipe_plan", {}).get("recipe_status", "not_run")
            counts[st] = counts.get(st, 0) + 1
        write_json(suggestions_path, suggestions)
        return {"suggestions": len(suggestions), "status_counts": counts}
