"""Multi-agent split of the pipeline that already exists.

Each agent is a function over a shared `Blackboard`. There is no framework here on purpose:
the ingestion, graph, planning and verification code already works, so an agent is a name and
a boundary, not a rewrite. Goose (or any orchestrator) can drive these as separate processes
later — the contract is the blackboard dict, which is JSON-serialisable end to end.

Agents:
    ingestion   clone/locate the repo, compile it, run the real detectors
    graph       build the dependency graph, attach severity to every finding
    refactor_rules      the existing evidence-gated planners  (deterministic)
    refactor_transformer  a separately-trained model's predictions, read from CSV
    validator   apply, rebuild, re-detect, keep only what compiled AND helped
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Callable, Dict, List

# Designite/Arcan report severity as words; the transformer reports ATDI-weighted floats.
# Map both onto one scale so a single ranking can order everything.
_WORD_SEVERITY = {"critical": 4.0, "high": 3.0, "medium": 2.0, "low": 1.0}
_SEVERITY_RE = re.compile(r"Severity:\s*([0-9]+(?:\.[0-9]+)?)")


def severity_of(finding: Dict[str, Any]) -> float:
    """One numeric severity for a finding, whatever produced it."""
    s = finding.get("severity")
    if isinstance(s, (int, float)):
        return float(s)
    if isinstance(s, str):
        try:
            return float(s)
        except ValueError:
            pass
        return _WORD_SEVERITY.get(s.lower(), 2.0)
    m = _SEVERITY_RE.search(finding.get("description") or "")
    return float(m.group(1)) if m else 2.0


def rank_by_severity(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Worst first. Ties keep detector order, so the ranking is reproducible."""
    return sorted(findings, key=lambda f: -severity_of(f))


# --------------------------------------------------------------------------- #
# agents
# --------------------------------------------------------------------------- #
def ingestion_agent(bb: Dict[str, Any]) -> Dict[str, Any]:
    """Locate the repo and run the REAL detectors on it."""
    from .config import load_config
    from .repositories.manager import RepositoryManager
    from .verification.openrewrite_loop import detect, detect_build_system

    cfg = bb.get("cfg") or load_config("local")
    repo = bb.get("repo_path")
    if not repo:
        mgr = RepositoryManager(cfg.data_dir)
        if bb.get("repo_url"):
            mgr.clone(bb["project_id"], bb["repo_url"], depth=1)
        repo = mgr.path_for(bb["project_id"])
    repo = Path(repo)
    out = cfg.data_dir / "outputs" / bb["project_id"] / "multiagent"
    before = detect(repo, out / "before", bb.get("detector", "both"))
    bb.update(cfg=cfg, repo_path=repo, out=out, before=before,
              build_system=detect_build_system(repo),
              findings=before.get("findings") or [])
    return bb


def graph_agent(bb: Dict[str, Any]) -> Dict[str, Any]:
    """Attach the dependency graph and order findings by severity."""
    from .graphs.builder import DependencyGraphBuilder
    from .source_index.indexer import SourceIndexer

    idx = SourceIndexer().index(bb["project_id"], bb["repo_path"])
    bb["graph"] = DependencyGraphBuilder().build(idx.import_edges)
    bb["findings"] = rank_by_severity(bb["findings"])
    return bb


def refactor_rules_agent(bb: Dict[str, Any]) -> Dict[str, Any]:
    """The existing evidence-gated planners. Deterministic, no model."""
    from .refactoring.agents import plan_all

    routed = plan_all(bb["repo_path"], bb["findings"], outputs_dir=bb["cfg"].data_dir / "outputs")
    bb["rule_plans"] = routed["plans"]
    bb["coverage"] = routed.get("coverage")
    return bb


def refactor_transformer_agent(bb: Dict[str, Any]) -> Dict[str, Any]:
    """Read the separately-trained model's predictions for this project.

    The model names refactoring TYPES (Extract Method, Move Class, …) with confidences; it
    does not emit executable recipes. So these are advisory: they are matched to findings and
    carried through for ranking and explanation, and the validator never executes them
    directly. Treating a 0.51-confidence type name as a recipe would be exactly the
    hallucination this project exists to avoid.
    """
    path = Path(bb.get("predictions_csv")
                or bb["cfg"].data_dir / "raw" / "predictions" / "transformer_predictions.csv")
    preds: List[Dict[str, Any]] = []
    if path.exists():
        want = bb["project_id"].replace("apache-", "")
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if want not in (row.get("project") or ""):
                    continue
                top = (row.get("suggestions") or "").split("|")[0].strip()
                m = re.match(r"(.+?)\s*\(([0-9.]+)\)", top)
                preds.append({
                    "smell_type": row.get("architecture_smell"),
                    "components": (row.get("affected_elements") or "").split("|"),
                    "refactoring": m.group(1) if m else top,
                    "confidence": float(m.group(2)) if m else None,
                    "severity": severity_of({"description": row.get("input_text")}),
                    "source": "transformer",
                    "executable": False,
                })
    bb["transformer_plans"] = sorted(preds, key=lambda p: -p["severity"])
    return bb


def validator_agent(bb: Dict[str, Any]) -> Dict[str, Any]:
    """Apply the executable plans for real, rebuild, re-detect, keep only what helped."""
    from .verification.openrewrite_loop import refactor_with_openrewrite_and_verify

    bb["report"] = refactor_with_openrewrite_and_verify(
        bb["cfg"], f"{bb['project_id']}__multiagent", bb["repo_path"],
        detector=bb.get("detector", "both"), keep_copy=True,
        known_before=bb.get("before"), plan_budget=bb.get("budget", 0),
        only_smells=bb.get("only_smells"))
    return bb


PIPELINE: List[Callable[[Dict[str, Any]], Dict[str, Any]]] = [
    ingestion_agent, graph_agent, refactor_rules_agent,
    refactor_transformer_agent, validator_agent,
]


def orchestrate(project_id: str, **kw) -> Dict[str, Any]:
    """Run every agent in order over one shared blackboard.

    Sequential because each agent needs the previous one's output — there is nothing to
    parallelise until two refactoring agents can propose against the same findings, which is
    what `rule_plans` and `transformer_plans` already set up.
    """
    bb: Dict[str, Any] = {"project_id": project_id, **kw}
    for agent in PIPELINE:
        bb = agent(bb)
        print(f"[{agent.__name__}] ok", flush=True)
    return bb
