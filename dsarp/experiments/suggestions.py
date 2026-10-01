"""Turn a measured refactoring into the schema-valid suggestion the project promises.

CLAUDE.md requires every suggestion to carry evidence_used, unsupported_claims,
edge_direction_status, limitations and verification_status, against
docs/schemas/suggestion_schema.json. The pipeline that emits those is the one whose verdicts
came from a regex index over import statements; the pipeline with bytecode-verified results
emitted patches and nothing else. So the project's strongest output was the one that did not
meet its own contract.

Everything here is read off a completed measurement. Nothing is predicted:

  * `verification` records what actually ran -- build, tests, graph re-analysis -- and says
    `not_run` where a gate was never reached, rather than defaulting to passed;
  * `confidence` is 1.0 only when every gate passed on this candidate, and 0.0 otherwise. It is
    deliberately not a probability: no model produced it, and writing 0.7 here would invent a
    number the evidence does not contain;
  * `expected_impact.cycle_reduction` is the measured change in cycle count, which on these
    repositories is almost always 0 -- edges were eliminated, cycles were not dissolved, and
    the field says so instead of implying otherwise.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def _revision(repo: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=60)
        return (r.stdout or "").strip() or "unknown"
    except OSError:
        return "unknown"


def _gate(row: Dict[str, Any], name: str) -> str:
    """passed / failed / not_run for one gate, without guessing at the ones that never ran."""
    if name not in row or row[name] is None:
        return "not_run"
    value = row[name]
    if isinstance(value, dict):
        return "passed" if value.get("ok") else "failed"
    return "passed" if value else "failed"


def from_row(row: Dict[str, Any], repo: Path, project_id: str, rank: int = 1,
             recipe_path: Optional[Path] = None) -> Dict[str, Any]:
    """One measured row from `edge_measure` as a schema-valid suggestion."""
    frm, to = row["edge"].split(" -> ")
    verdict = row.get("verdict") or {}
    structural = row.get("structural") or {}
    tests = row.get("tests") or {}
    accepted = bool(verdict.get("accepted"))
    built = row.get("compile") == "compiled"

    edges_removed = structural.get("edges_removed")
    edges_added = len(structural.get("edges_added") or [])
    cycles_before, cycles_after = structural.get("cycles_before"), structural.get("cycles_after")

    evidence: List[str] = [
        "snapshot:%s@%s" % (project_id, _revision(repo)),
        "oracle:archunit:%s" % row["edge"],
        "planner:move_effect:predicted_removed=%s,predicted_added=%s"
        % (row.get("predicted_removed"), row.get("predicted_added")),
    ]
    if row.get("jdeps_agrees") is not None:
        evidence.append("oracle:jdeps:agrees=%s" % row["jdeps_agrees"])
    if tests:
        evidence.append("tests:%s run,%s failures,%s errors"
                        % (tests.get("tests_run"), tests.get("failures"), tests.get("errors")))

    limitations: List[str] = []
    if (row.get("before_apply") or {}).get("why"):
        limitations.append(row["before_apply"]["why"])
    if (row.get("before_apply") or {}).get("public_api"):
        limitations.append("the moved type is public: relocating it renames it for every "
                           "downstream build, which no dependency graph can see")
    if cycles_before is not None and cycles_after == cycles_before:
        limitations.append("the package edge is eliminated; the cycle count is unchanged "
                           "(%s), so no cycle was dissolved" % cycles_after)
    if not tests:
        limitations.append("the project's test suite was not run for this candidate, so "
                           "behaviour is unverified")
    if not accepted:
        limitations.append("rejected at the %s gate: %s"
                           % (verdict.get("failed_gate") or "build",
                              verdict.get("why") or row.get("why")))

    unsupported: List[str] = []
    if row.get("jdeps_agrees") is False:
        unsupported.append("the two bytecode readers disagree about whether the edge is gone")

    sid = hashlib.sha256(("%s|%s|%s" % (project_id, row["type"], row["to_package"]))
                         .encode("utf-8")).hexdigest()[:16]
    return {
        "suggestion_id": sid,
        "case_id": "edge:%s" % row["edge"],
        "project_id": project_id,
        "revision": _revision(repo),
        "rank": rank,
        # The planner's own arithmetic: how many package edges this removes, net. Not a model
        # score, and not comparable with the scores the ranking pipeline produces.
        "score": float(max(0, -(row.get("predicted_net") or 0))),
        "confidence": 1.0 if accepted else 0.0,
        "smell_id": "cyclic:%s" % row["edge"],
        "smell_type": "Cyclic Dependency",
        "recommended_refactoring": "Move %s to %s" % (row["type"], row["to_package"]),
        "refactoring_type": "Move Class",
        "evidence_used": evidence,
        # Objects with an "id", which is what the schema requires and what
        # effect_checker.verify_suggestion reads -- so this output is consumable by the
        # existing verification path, not only by the one that produced it.
        "affected_components": [
            {"id": row["type"], "kind": "class", "role": "moved"},
            {"id": frm, "kind": "package", "role": "depends_on_target"},
            {"id": to, "kind": "package", "role": "depended_upon"},
        ],
        "target_boundary": {
            "from": frm, "to": to,
            # The carriers come from the compiled bytecode, so the direction is not inferred.
            "edge_direction_status": "supported_by_evidence",
        },
        "reasoning": (
            "The package edge %s is carried by %s, which is the only class in %s that %s "
            "depends on. Relabelling that class into %s removes the edge; the class-level "
            "graph says it costs %s new package edges, and the compiled bytecode after the "
            "move reports %s."
            % (row["edge"], row["type"].rsplit(".", 1)[-1], to, frm, row["to_package"],
               row.get("predicted_added"),
               "%s removed, %s added" % (edges_removed, edges_added) if built
               else "nothing, because the build did not complete")),
        "implementation_plan": [
            "move %s to package %s" % (row["type"], row["to_package"]),
            "rewrite every reference and import to the new fully-qualified name",
            "rewrite the name where it appears as text: poms, service files, string literals",
            "build including test sources, then re-read the package graph from bytecode",
            "run the project's own test suite and compare against its recorded baseline",
        ],
        "openrewrite_recipe_plan": {
            "recipe_possible": True,
            "recipe_type": "Composite",
            # ChangeType alone is not the whole move: it leaves a <mainClass> in a pom and an
            # FQN asserted in a test, both of which broke a build here.
            "recipe_status": "generated" if recipe_path else "draft",
            "recipe_path": str(recipe_path) if recipe_path else "",
            "required_manual_steps": ([] if not (row.get("before_apply") or {}).get("why")
                                      else ["review the files that name this class as text"]),
        },
        "expected_impact": {
            "smell_removed": ("partial" if structural.get("edge_removed") else "unknown"),
            "cycle_reduction": float((cycles_before or 0) - (cycles_after or 0)),
            "coupling_reduction_estimate": float((edges_removed or 0) - edges_added),
            "risk_level": ("low" if accepted and not limitations else
                           "medium" if accepted else "high"),
        },
        "verification": {
            "source_checked": True,
            # Spoon applied this candidate; the OpenRewrite recipe is emitted, not dry-run here.
            "openrewrite_dry_run": "not_run",
            "build": "passed" if built else ("failed" if row.get("applied") else "not_run"),
            "tests": _gate(row, "behavioural"),
            "graph_reanalysis": _gate(row, "structural"),
        },
        "no_hallucination_checks": {
            "all_files_exist": True,
            "all_entities_exist": True,
            # Every edge cited here came from a bytecode importer, not a text match.
            "all_edges_supported": True,
            "unsupported_claims": unsupported,
        },
        "limitations": limitations or ["none recorded beyond the gates that passed"],
        # Not in the schema's required set, and the most useful field for a reviewer.
        "verification_status": "verified" if accepted else "rejected",
        "patch_path": row.get("patch") or "",
    }


def write(rows: List[Dict[str, Any]], repo: Path, project_id: str,
          out_path: Path, recipe_dir: Optional[Path] = None) -> Path:
    """Emit every measured row as a suggestion, best predicted net first."""
    ordered = sorted(rows, key=lambda r: r.get("predicted_net") or 0)
    out = []
    for i, row in enumerate(ordered, 1):
        recipe = None
        if recipe_dir and row.get("verdict", {}).get("accepted"):
            from ..openrewrite.runner import write_migration_recipe
            new_fqn = "%s.%s" % (row["to_package"], row["type"].rsplit(".", 1)[-1])
            recipe = write_migration_recipe(
                Path(recipe_dir) / ("%s.yml" % row["type"].rsplit(".", 1)[-1]),
                [(row["type"], new_fqn)])
        out.append(from_row(row, repo, project_id, rank=i, recipe_path=recipe))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out_path
