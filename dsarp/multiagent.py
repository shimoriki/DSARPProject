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


def consensus(rule_plans, transformer_plans) -> Dict[str, Any]:
    """Which rule plans a second, independently-trained model also flagged.

    Agreement is on WHAT to fix, not how. The transformer names method-level refactorings
    (Move And Rename Method, Extract Method) while the rule agent relocates packages and
    classes, so matching on refactoring name would agree essentially never - 658 of 716
    log4j2 predictions are Move And Rename Method. Two models pointing at the same smell in
    the same component IS the signal; expecting them to name the same transformation is not.
    """
    def parts(c: str):
        """Both endpoints of a component string.

        Relocation plans record a component as the move itself - "a.b -> a" - while the
        transformer reports bare package names. Comparing the raw strings finds nothing even
        when both models named the same package, which is what made log4j2 report 0 agreed
        out of 307 on the first run.
        """
        return [x.strip() for x in str(c).split("->") if x.strip()]

    seen = {}
    for t in transformer_plans:
        for c in t.get("components") or []:
            for part in parts(c):
                seen.setdefault((str(t.get("smell_type", "")).lower(), part), t)
    agreed, solo = [], []
    for p in rule_plans:
        if not getattr(p, "applicable", False):
            continue
        smell = str(getattr(p, "smell_type", "")).lower()
        hit = next((seen[(smell, part)]
                    for c in (getattr(p, "components", None) or [])
                    for part in parts(c) if (smell, part) in seen), None)
        (agreed if hit else solo).append((p, hit))
    return {"agreed": agreed, "rule_only": solo}


def validator_agent(bb: Dict[str, Any]) -> Dict[str, Any]:
    """Apply the executable plans for real, rebuild, re-detect, keep only what helped."""
    from .verification.iterative_loop import run_until_converged, DEFAULT_SMELL_ORDER

    agree = consensus(bb.get("rule_plans") or [], bb.get("transformer_plans") or [])
    bb["consensus"] = {"agreed": len(agree["agreed"]), "rule_only": len(agree["rule_only"])}

    # The iterative loop IS the validator: it re-detects and re-plans between passes, keeps a
    # pass only when the build still compiles and the targeted smells actually fell, and rolls
    # back everything else. A single pass could not do the second half of that.
    order = DEFAULT_SMELL_ORDER if bb.get("by_smell") else None
    if bb.get("require_consensus") and agree["agreed"]:
        order = [t for t in (order or DEFAULT_SMELL_ORDER)
                 if t in {getattr(p, "smell_type") for p, _ in agree["agreed"]}] or order

    bb["report"] = run_until_converged(
        bb["cfg"], f"{bb['project_id']}__multiagent", bb["repo_path"],
        detector=bb.get("detector", "both"), max_passes=bb.get("max_passes", 5),
        smell_order=order)

    # Strategy 2: for smells no rule plan covered, let the LLM path propose - it composes
    # from a fixed recipe allowlist and is judged by the same build+measure gate, so it adds
    # coverage without adding trust. Only runs when asked, since it costs model calls.
    if bb.get("use_ai_recipes"):
        from .refactoring.ai_recipes import propose, test_proposal
        from .refactoring.strategies import SourceFacts
        from .models import get_provider
        covered = {getattr(p, "smell_type") for p in (bb.get("rule_plans") or [])
                   if getattr(p, "applicable", False)}
        facts = SourceFacts(bb["repo_path"])
        model = get_provider(bb.get("model") or {"type": "offline"})
        trials = []
        for f in bb["findings"]:
            if f.get("smell_type") in covered or len(trials) >= bb.get("ai_budget", 3):
                continue
            prop = propose(model, facts, f)
            trials.append(test_proposal(bb["cfg"], f"{bb['project_id']}__ai",
                                        bb["repo_path"], prop, bb.get("detector", "both"))
                          if not prop.rejection else
                          {"verdict": "rejected", "why": prop.rejection,
                           "smell_type": f.get("smell_type")})
        bb["ai_trials"] = trials
    return bb


# The transformer agent is opt-in (`use_transformer=True`). Its predictions only cover the
# repositories it was trained on, and on everything else it contributes nothing while making
# the run look like it consulted two models.
PIPELINE: List[Callable[[Dict[str, Any]], Dict[str, Any]]] = [
    ingestion_agent, graph_agent, refactor_rules_agent, validator_agent,
]


def orchestrate(project_id: str, **kw) -> Dict[str, Any]:
    """Run every agent in order over one shared blackboard.

    Sequential because each agent needs the previous one's output — there is nothing to
    parallelise until two refactoring agents can propose against the same findings, which is
    what `rule_plans` and `transformer_plans` already set up.
    """
    from .refactoring.outcomes import build_ledger
    from .util import write_json

    bb: Dict[str, Any] = {"project_id": project_id, **kw}
    pipeline = list(PIPELINE)
    if bb.get("use_transformer"):
        pipeline.insert(pipeline.index(validator_agent), refactor_transformer_agent)
    for agent in pipeline:
        bb = agent(bb)
        print(f"[{agent.__name__}] ok", flush=True)

    # What the orchestrator carries into the next iteration. The ledger is the real memory -
    # it already aggregates measured effect per (smell, refactoring) over every verified run,
    # and rank_plans consults it - so this records the run and leaves the learning where it
    # already works rather than inventing a second store that could disagree with it.
    rep = bb.get("report") or {}
    memory = {
        "project_id": project_id,
        "findings": len(bb.get("findings") or []),
        "rule_applicable": sum(1 for p in (bb.get("rule_plans") or [])
                               if getattr(p, "applicable", False)),
        "transformer_predictions": len(bb.get("transformer_plans") or []),
        "consensus": bb.get("consensus"),
        "passes_run": rep.get("passes_run"), "passes_accepted": rep.get("passes_accepted"),
        "smells_before": rep.get("architectural_smells_before"),
        "smells_after": rep.get("architectural_smells_after"),
        "reduction_pct": rep.get("reduction_pct"),
        "smell_types_kept": sorted({t for p in (rep.get("passes") or []) if p.get("accepted")
                                    for t in (p.get("smell_types_refactored") or [])}),
        "ai_trials": [t.get("verdict") for t in (bb.get("ai_trials") or [])],
        "ledger_entries": len(build_ledger(bb["cfg"].data_dir / "outputs")),
    }
    write_json(bb["out"] / "orchestrator_memory.json", memory)
    bb["memory"] = memory
    return bb
