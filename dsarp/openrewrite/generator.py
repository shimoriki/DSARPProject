"""Loop 11 — OpenRewrite recipe generation.

Generates a recipe artefact per candidate where OpenRewrite can genuinely help
(rename/move/package/imports). Design-heavy refactorings get a manual plan, not a
faked automatic recipe. Every recipe is marked draft until dry-run/build/test pass.

Recipe status lifecycle: draft -> generated -> validated | failed | not_applicable
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from ..candidates.generator import Candidate

# Which candidate refactoring types OpenRewrite can (partially) automate.
_AUTOMATABLE = {
    "Move Class": ("YAML", "org.openrewrite.java.ChangeType / MoveClass"),
    "Extract Interface": ("Java visitor", "custom ExtractInterface visitor (manual body)"),
}


class OpenRewriteGenerator:
    def __init__(self, out_dir: Path):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def plan(self, candidate: Candidate) -> Tuple[Dict, str]:
        """Returns (openrewrite_recipe_plan dict, recipe_text_or_empty)."""
        rtype = candidate.recommended_refactoring
        if rtype not in _AUTOMATABLE:
            return ({
                "recipe_possible": False, "recipe_type": "Not applicable",
                "recipe_status": "not_applicable", "recipe_path": "",
                "required_manual_steps": self._manual_steps(candidate),
            }, "")
        kind, recipe_name = _AUTOMATABLE[rtype]
        text = self._render(candidate, kind, recipe_name)
        path = self.out_dir / f"{candidate.candidate_id}.{'yml' if kind == 'YAML' else 'java'}.txt"
        path.write_text(text, encoding="utf-8")
        return ({
            "recipe_possible": True, "recipe_type": kind,
            "recipe_status": "draft",  # never 'validated' without a real dry-run
            "recipe_path": str(path),
            "required_manual_steps": self._manual_steps(candidate),
        }, text)

    def _render(self, c: Candidate, kind: str, recipe_name: str) -> str:
        b = c.target_boundary
        if kind == "YAML":
            return (
                "# DRAFT OpenRewrite recipe — requires dry-run/build/test validation.\n"
                "# Exact fully-qualified names require source inspection.\n"
                "type: specs.openrewrite.org/v1beta/recipe\n"
                f"name: com.dsarp.generated.{c.candidate_id}\n"
                f"displayName: {c.recommended_refactoring} for {c.smell_type}\n"
                "recipeList:\n"
                "  - org.openrewrite.java.ChangeType:\n"
                f"      oldFullyQualifiedTypeName: <REQUIRES_SOURCE_INSPECTION: type in {b.get('from','?')}>\n"
                f"      newFullyQualifiedTypeName: <REQUIRES_SOURCE_INSPECTION: target in {b.get('to','?')}>\n"
            )
        return (
            "// DRAFT OpenRewrite Java visitor plan — body requires source inspection.\n"
            f"// Recipe: {recipe_name}\n"
            f"// Goal: {c.recommended_refactoring} to address {c.smell_type}\n"
            f"// Boundary: from={b.get('from','?')} to={b.get('to','?')} "
            f"(status={b.get('edge_direction_status')})\n"
            "// Steps: 1) extract interface from concrete type; 2) retarget dependents;\n"
            "//        3) verify no cycle remains (graph re-analysis).\n"
        )

    def _manual_steps(self, c: Candidate) -> List[str]:
        return [
            f"Inspect source to confirm exact entities in {c.affected_components[:3]}.",
            "Confirm edge direction before moving/inverting the dependency.",
            "Run OpenRewrite dry-run, then Maven compile + tests.",
            "Re-run dependency graph analysis to confirm smell reduction.",
        ]
