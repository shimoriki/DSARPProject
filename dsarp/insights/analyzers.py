"""Task 15 — insight analyzers. Pure functions over existing evidence/outputs.

None of these invent evidence: they summarise, compare, or reformat data the
pipeline already produced. Each returns plain dicts/strings for CLI + UI.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..schemas import DependencyGraph, EvidenceCase


# 2. Architecture Health Radar -------------------------------------------- #
def architecture_health_radar(case: EvidenceCase) -> Dict[str, Any]:
    g = case.dependency_graph
    gm = g.graph_metrics
    nodes = g.nodes
    avg_inst = round(sum(n.metrics.get("instability", 0.0) for n in nodes) / len(nodes), 3) if nodes else 0.0
    max_fan = max((n.metrics.get("fan_in", 0) + n.metrics.get("fan_out", 0) for n in nodes), default=0)
    unstable = [n.id for n in nodes if n.metrics.get("instability", 0) > 0.7]
    return {
        "project_id": case.project_id,
        "cycles": gm.get("cycle_count", 0),
        "sccs": gm.get("scc_count", 0),
        "smell_count": len(case.smells),
        "avg_instability": avg_inst,
        "max_coupling": max_fan,
        "unstable_components": unstable[:10],
        "radar": {  # 0..1 axes for a radar chart
            "cyclicity": min(1.0, gm.get("cycle_count", 0) / 10),
            "coupling": min(1.0, max_fan / 20),
            "instability": avg_inst,
            "smell_density": min(1.0, len(case.smells) / 20),
        },
    }


# 4. Evidence Conflict Detector ------------------------------------------- #
def evidence_conflict_detector(case: EvidenceCase) -> List[Dict[str, Any]]:
    """Flag components where tools overlap but report different smell types,
    or where only one of Arcan/Designite fired on a shared component."""
    conflicts: List[Dict[str, Any]] = []
    by_comp: Dict[str, List] = {}
    for s in case.smells:
        for c in s.affected_components:
            by_comp.setdefault(c, []).append(s)
    for comp, smells in by_comp.items():
        tools = {t for s in smells for t in s.tool_sources}
        types = {s.smell_type for s in smells}
        if len(types) > 1 and len(tools) > 1:
            conflicts.append({"component": comp, "smell_types": sorted(types),
                              "tools": sorted(tools), "kind": "overlapping_different_smells"})
        elif len(tools) == 1 and "DependencyGraph" not in tools:
            conflicts.append({"component": comp, "smell_types": sorted(types),
                              "tools": sorted(tools), "kind": "single_tool_only"})
    return conflicts


# 3. Refactoring Pattern Library ------------------------------------------ #
def refactoring_pattern_library(alignments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Priors from historical alignments: common refactorings per smell type."""
    by_smell: Dict[str, Dict[str, int]] = {}
    for a in alignments:
        st = a.get("smell_type", "?")
        rt = a.get("refactoring_type", "?")
        conf = a.get("alignment_confidence", 0)
        if conf < 0.5:
            continue
        by_smell.setdefault(st, {}).setdefault(rt, 0)
        by_smell[st][rt] += 1
    priors = {st: sorted(rts.items(), key=lambda kv: -kv[1]) for st, rts in by_smell.items()}
    return {"priors_by_smell": priors,
            "top_refactoring_per_smell": {st: rts[0][0] for st, rts in priors.items() if rts}}


# 1. Active Learning Queue ------------------------------------------------- #
def active_learning_queue(suggestions: List[Dict[str, Any]], threshold: float = 0.2) -> List[Dict[str, Any]]:
    """Rank suggestions where graph vs ranker scores disagree most -> review first."""
    queue = []
    for s in suggestions:
        rb = s.get("rank_breakdown", {})
        graph_s = rb.get("graph_score", 0.0)
        ranker_s = rb.get("ranker_score", -1.0)
        if ranker_s < 0:  # no learned score
            continue
        disagreement = abs(graph_s - ranker_s)
        if disagreement >= threshold:
            queue.append({"suggestion_id": s["suggestion_id"], "smell_type": s["smell_type"],
                          "refactoring": s["recommended_refactoring"],
                          "disagreement": round(disagreement, 3),
                          "graph_score": graph_s, "ranker_score": ranker_s})
    return sorted(queue, key=lambda d: -d["disagreement"])


# 7. Repository Readiness Score ------------------------------------------- #
def repository_readiness_score(suggestions: List[Dict[str, Any]], build_system: str = "unknown",
                               source_index_available: bool = False) -> Dict[str, Any]:
    n = len(suggestions) or 1
    recipe_ready = sum(1 for s in suggestions
                       if s.get("openrewrite_recipe_plan", {}).get("recipe_possible")) / n
    grounded = sum(1 for s in suggestions
                   if not s.get("no_hallucination_checks", {}).get("unsupported_claims")) / n
    build_bonus = {"maven": 0.3, "gradle": 0.2, "plain-java": 0.1}.get(build_system, 0.0)
    score = round(min(1.0, 0.4 * recipe_ready + 0.3 * grounded
                      + build_bonus + (0.2 if source_index_available else 0.0)), 3)
    verdict = ("automation-friendly" if score > 0.6
               else "manual-plans-recommended" if score < 0.4 else "mixed")
    return {"readiness_score": score, "verdict": verdict,
            "recipe_ready_ratio": round(recipe_ready, 3), "build_system": build_system,
            "source_index_available": source_index_available}


# 9. Recipe Risk Meter ----------------------------------------------------- #
def recipe_risk_meter(suggestion: Dict[str, Any]) -> Dict[str, Any]:
    rb = suggestion.get("rank_breakdown", {})
    impact = suggestion.get("expected_impact", {})
    risk = rb.get("risk", 0.5)
    edge_ok = suggestion.get("edge_direction_status") == "supported_by_evidence"
    automatable = suggestion.get("openrewrite_recipe_plan", {}).get("recipe_possible", False)
    meter = round(min(1.0, 0.6 * risk + (0.0 if edge_ok else 0.2)
                      + (0.0 if automatable else 0.2)), 3)
    band = "safe" if meter < 0.35 else "risky" if meter > 0.65 else "caution"
    return {"risk_meter": meter, "band": band, "risk_level": impact.get("risk_level"),
            "edge_supported": edge_ok, "automatable": automatable}


# 11. Graph Delta Preview -------------------------------------------------- #
def graph_delta_preview(suggestion: Dict[str, Any], graph: DependencyGraph) -> Dict[str, Any]:
    rb = suggestion.get("rank_breakdown", {})
    delta = rb.get("graph_delta", 0.0)
    before = graph.graph_metrics.get("cycle_count", 0)
    est_removed = round(delta, 2)
    after = max(0, round(before - before * delta))
    return {"cycles_before": before, "estimated_cycles_after": after,
            "estimated_coupling_reduction": round(delta * 0.5, 3),
            "estimated_edges_removed_fraction": est_removed,
            "note": "estimate from graph delta; confirm via post-refactor graph re-analysis"}


# 10. Issue/PR Draft Generator (no pushing) ------------------------------- #
def issue_pr_draft(suggestion: Dict[str, Any]) -> str:
    comps = [c.get("id") for c in suggestion.get("affected_components", [])][:5]
    plan = suggestion.get("implementation_plan", [])
    ev = suggestion.get("evidence_used", [])
    body = [
        f"## Refactoring proposal: {suggestion.get('recommended_refactoring')} "
        f"for {suggestion.get('smell_type')}", "",
        f"**Confidence:** {suggestion.get('confidence')} · "
        f"**Risk:** {suggestion.get('expected_impact', {}).get('risk_level')} · "
        f"**Verification:** {suggestion.get('verification_status')}", "",
        "### Affected components", *[f"- `{c}`" for c in comps], "",
        "### Rationale (evidence-grounded)", suggestion.get("reasoning", ""), "",
        f"**Evidence:** {', '.join(ev) or 'requires_source_inspection'}", "",
        "### Suggested steps", *[f"1. {s}" for s in plan], "",
        "### Limitations", *[f"- {l}" for l in suggestion.get("limitations", []) or ["none"]], "",
        "_Draft generated by DSARP. Not automatically pushed. Review before opening._",
    ]
    return "\n".join(body)


# 8. No-Hallucination Leaderboard ----------------------------------------- #
def no_hallucination_leaderboard(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """runs: [{provider, suggestions:[...]}] -> ranked by grounding + validity."""
    board = []
    for run in runs:
        sugs = run.get("suggestions", [])
        n = len(sugs) or 1
        grounded = sum(1 for s in sugs
                       if not s.get("no_hallucination_checks", {}).get("unsupported_claims")) / n
        unsupported = sum(len(s.get("no_hallucination_checks", {}).get("unsupported_claims", []))
                          for s in sugs)
        board.append({"provider": run.get("provider"), "grounding_pass_rate": round(grounded, 3),
                      "unsupported_claims": unsupported, "suggestions": len(sugs)})
    return sorted(board, key=lambda d: (-d["grounding_pass_rate"], d["unsupported_claims"]))
