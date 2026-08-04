"""End-to-end pipeline for ANY repo, with a result recorded at EVERY step.

  1 acquire (clone/read)  2 detect smells (Arcan output if present, else structural)
  3 dependency graph      4 suggest for ALL smell types
  5 OpenRewrite recipes    6 apply (source Move Class / graph-sim design refactorings)
  7 re-detect smells       8 compare (removed? cumulative tangle reduction)

Honest about tooling: Arcan/OpenRewrite EXECUTE-mode is wired but needs the JVM binaries; when
absent we use the imported Arcan smells + the structural detector (same smell definitions) and the
deterministic applier (equivalent to OpenRewrite's move/change recipes). Each step records which
engine actually ran.
"""
from __future__ import annotations

import collections
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config
from .inference.unseen import detect_build_system, prepare_evidence
from .memory import ProjectMemory
from .openrewrite.generator import OpenRewriteGenerator
from .pipeline import InferencePipeline
from .repositories.manager import RepositoryManager
from .schemas import EvidenceCase
from .util import read_json, write_json


def _step(n: int, title: str, tool: str, status: str, summary: str, **detail) -> Dict[str, Any]:
    return {"step": n, "title": title, "tool": tool, "status": status,
            "summary": summary, "detail": detail}


def run_pipeline(cfg: Config, project_id: str, repo_url: Optional[str] = None,
                 repo_path: Optional[Path] = None, top_k: int = 8) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = []
    rm = RepositoryManager(cfg.data_dir)

    # 1 — acquire ----------------------------------------------------------- #
    if repo_url and not repo_path:
        dest = rm.path_for(project_id)
        if not (dest.exists() and any(dest.rglob("*.java"))):
            rm.clone(project_id if "/" in project_id else project_id, url=repo_url, depth=1)
        repo_path = dest
    repo_path = Path(repo_path) if repo_path else rm.path_for(project_id)
    has_src = repo_path.exists() and any(repo_path.rglob("*.java"))
    build = detect_build_system(repo_path) if has_src else "unknown"
    steps.append(_step(1, "Acquire repository", "git", "ok" if has_src else "failed",
                       f"{project_id}: {'source present' if has_src else 'no source'} "
                       f"(build system: {build})", path=str(repo_path), build_system=build))
    if not has_src:
        return {"project_id": project_id, "steps": steps, "ok": False}

    # 2 & 3 — detect smells + graph (prepare_evidence merges Arcan/Designite + structural) --- #
    prep = prepare_evidence(cfg, project_id, repo_path=repo_path)
    case = EvidenceCase(**read_json(cfg.data_dir / "normalized" / f"{project_id}.json"))
    by_type = collections.Counter(s.smell_type for s in case.smells)
    arcan_smells = [s for s in case.smells if "Arcan" in s.tool_sources]
    detect_tool = ("Arcan (imported output)" if arcan_smells
                   else "structural detector (graph-based)")
    steps.append(_step(2, "Detect architectural smells", detect_tool, "ok",
                       f"{len(case.smells)} smells across {len(by_type)} types "
                       f"({len(arcan_smells)} from Arcan)",
                       by_type=dict(by_type), tools_used=prep.get("tools_used"),
                       tools_unavailable=prep.get("tools_unavailable")))
    gm = case.dependency_graph.graph_metrics
    steps.append(_step(3, "Build dependency graph", "NetworkX", "ok",
                       f"{gm.get('node_count')} packages, {gm.get('edge_count')} edges, "
                       f"{gm.get('cycle_count')} cycles, {gm.get('scc_count')} SCCs",
                       **{k: gm.get(k) for k in ("node_count", "edge_count", "cycle_count", "scc_count")}))

    # 4 — suggestions for ALL smell types ----------------------------------- #
    mem = ProjectMemory(cfg.data_dir, project_id)
    # offline explainer: on a repo with 100+ smells this is 100s of calls; the closed-loop test
    # is about the refactoring EFFECT, not prose, so keep it fast/deterministic.
    pipe = InferencePipeline(cfg, top_k_per_smell=3, model_override={"type": "offline"})
    suggestions, opt = pipe.run(case, mem.memory_ref(case.revision))
    sug_by_type = collections.Counter(s.smell_type for s in suggestions)
    top = [{"rank": s.rank, "smell": s.smell_type, "refactoring": s.recommended_refactoring,
            "score": s.score, "components": [c.get("id") for c in s.affected_components][:2],
            "suggestion_id": s.suggestion_id} for s in suggestions[:top_k]]
    write_json(cfg.data_dir / "outputs" / project_id / "suggestions.json",
               [s.to_contract_dict() for s in suggestions])
    steps.append(_step(4, "Generate refactoring suggestions (all smell types)", "DSARP ranker",
                       "ok", f"{len(suggestions)} ranked suggestions for {len(sug_by_type)} smell types",
                       by_smell_type=dict(sug_by_type), top=top))

    # 5 — OpenRewrite recipes ---------------------------------------------- #
    gen = OpenRewriteGenerator(cfg.data_dir / "outputs" / project_id / "recipes")
    from .candidates.generator import Candidate
    recipes, possible = [], 0
    for s in suggestions[:top_k]:
        b = s.target_boundary
        cand = Candidate(candidate_id=s.suggestion_id, smell_id=s.smell_id, smell_type=s.smell_type,
                         refactoring_type=s.refactoring_type, recommended_refactoring=s.recommended_refactoring,
                         affected_components=[c.get("id") for c in s.affected_components],
                         target_boundary={"from": b.from_, "to": b.to,
                                          "edge_direction_status": b.edge_direction_status},
                         graph_delta_estimate=0.0, risk_score=0.0, recipe_applicable=True)
        plan, _ = gen.plan(cand)
        recipes.append({"refactoring": s.recommended_refactoring, "recipe_type": plan["recipe_type"],
                        "status": plan["recipe_status"], "path": plan.get("recipe_path", "")})
        possible += 1 if plan["recipe_possible"] else 0
    maven = _has_maven()
    steps.append(_step(5, "Generate OpenRewrite recipes", "OpenRewrite", "ok",
                       f"{possible}/{len(recipes)} suggestions have an OpenRewrite recipe; "
                       f"{'Maven available (can run)' if maven else 'Maven NOT installed -> recipes are drafts'}",
                       recipes=recipes, maven_available=maven))

    # 6, 7, 8 — apply, re-detect, compare ---------------------------------- #
    from .verification.effect_checker import verify_suggestion, snapshot_smells, simulate_cumulative
    from .source_index.indexer import SourceIndexer
    work = cfg.data_dir / "outputs" / project_id / "verify"
    sug_dicts = [s.to_contract_dict() for s in suggestions]
    # compute the baseline snapshot + source index ONCE (identical per suggestion) — avoids
    # re-indexing a large repo N times (the pipeline's main cost).
    base = snapshot_smells(repo_path, project_id)
    src_idx = read_json(cfg.data_dir / "source_index" / f"{project_id}.json", default=None) \
        or SourceIndexer().index(project_id, repo_path).to_dict()
    per = []
    for sd in sug_dicts[:top_k]:
        per.append(verify_suggestion(repo_path, sd, work, before=base, source_index=src_idx))
    applied_removed = sum(1 for r in per if r.get("smell_removed"))
    steps.append(_step(6, "Apply refactorings & re-check (per suggestion)",
                       "deterministic applier + graph re-analysis", "ok",
                       f"{applied_removed}/{len(per)} suggestions measurably removed a smell",
                       results=[{"refactoring": r["refactoring"], "method": r.get("applier"),
                                 "cycles_before": r.get("cycles_before"), "cycles_after": r.get("cycles_after"),
                                 "smell_removed": r.get("smell_removed")} for r in per]))
    write_json(cfg.data_dir / "outputs" / project_id / "verify_effect.json", per)

    cum = simulate_cumulative(base, sug_dicts, max_steps=max(top_k, 40))
    write_json(cfg.data_dir / "outputs" / project_id / "verify_cumulative.json", cum)
    steps.append(_step(7, "Re-detect smells after applying all suggestions (cumulative)",
                       "structural detector (graph re-analysis)", "ok",
                       f"packages-in-cycles {cum['packages_in_cycles_before']} -> "
                       f"{cum['packages_in_cycles_after']} ({cum['reduction_pct']}% freed); "
                       f"core tangle {cum['largest_tangle_before']} -> {cum['largest_tangle_after']} pkgs",
                       **{k: cum[k] for k in ("packages_in_cycles_before", "packages_in_cycles_after",
                                              "packages_freed", "reduction_pct",
                                              "largest_tangle_before", "largest_tangle_after", "steps")}))
    # before/after dependency graph (after = before graph minus the edges the refactorings broke)
    import networkx as nx
    removed = {tuple(pt["edge"].split("->")) for pt in cum["trajectory"] if pt.get("edge")}
    after_edges = [e for e in base.edges if (e["source"], e["target"]) not in removed]

    def _gm(edges):
        g = nx.DiGraph()
        for e in edges:
            g.add_edge(e["source"], e["target"])
        scc = [len(c) for c in nx.strongly_connected_components(g) if len(c) > 1]
        return {"packages": g.number_of_nodes(), "edges": g.number_of_edges(),
                "packages_in_cycles": sum(scc), "largest_tangle": max(scc) if scc else 0}

    gb, ga = _gm(base.edges), _gm(after_edges)
    write_json(cfg.data_dir / "outputs" / project_id / "graph_before_after.json",
               {"before": {"metrics": gb, "edges": base.edges},
                "after": {"metrics": ga, "edges": after_edges},
                "removed_edges": [f"{s}->{t}" for s, t in removed]})
    steps.append(_step(9, "Dependency graph — before vs after refactoring", "NetworkX", "ok",
                       f"edges {gb['edges']} -> {ga['edges']} ({len(removed)} broken); "
                       f"packages in cycles {gb['packages_in_cycles']} -> {ga['packages_in_cycles']}",
                       before=gb, after=ga, removed_edges=len(removed)))

    verdict = ("Fully untangled" if cum["packages_in_cycles_after"] == 0
               else f"{cum['reduction_pct']}% of tangled packages freed; irreducible core of "
                    f"{cum['largest_tangle_after']} packages remains (needs deep restructuring)")
    steps.append(_step(8, "Verdict", "DSARP", "ok", verdict,
                       smells_before=len(case.smells), suggestions=len(suggestions),
                       per_suggestion_removed=applied_removed))

    report = {"project_id": project_id, "ok": True, "build_system": build, "steps": steps}
    write_json(cfg.data_dir / "outputs" / project_id / "e2e_report.json", report)
    return report


def _has_maven() -> bool:
    """Maven on PATH, or the bundled tools/apache-maven-*/ we downloaded."""
    import shutil
    if shutil.which("mvn"):
        return True
    tools = Path(__file__).resolve().parent.parent / "tools"
    return bool(list(tools.glob("apache-maven-*/bin/mvn.cmd")) if tools.exists() else [])
