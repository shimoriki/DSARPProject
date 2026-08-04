"""Unified CLI. `dsarp-local` and `dsarp-hpc` are thin profile wrappers.

Subcommands map to the graph-of-loops. Heavy Java tools run in import mode locally;
HPC profile swaps providers/config only. Heavy imports (sklearn, fastapi) are lazy so
`--help` and light commands stay fast. Every light command is safe offline.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .config import Config, load_config, load_repo_entries
from .util import read_json, write_json


# --------------------------------------------------------------------------- #
# setup / db
# --------------------------------------------------------------------------- #
def cmd_setup(cfg: Config, args) -> int:
    for sub in ["raw", "normalized", "graphs", "refactoring_events", "aligned_examples",
                "training", "validation", "test", "outputs", "memory", "cache",
                "models", "reports", "source_index"]:
        (cfg.data_dir / sub).mkdir(parents=True, exist_ok=True)
    if not getattr(args, "_quiet", False):
        print(f"[setup] data dirs ready under {cfg.data_dir} (profile={cfg.profile})")
    return 0


def cmd_db(cfg: Config, args) -> int:
    from .db import Store
    store = Store(cfg.db_path)
    if args.sub == "init":
        print(f"[db] initialised schema v{store.init()} at {cfg.db_path}")
    elif args.sub == "status":
        st = store.status()
        print(f"[db] exists={st.get('exists')} version={st.get('schema_version')}")
        for t, n in st.get("row_counts", {}).items():
            print(f"     {t}: {n}")
    elif args.sub == "import-outputs":
        from .db.importer import import_outputs
        store.init()
        counts = import_outputs(cfg.data_dir, store)
        print(f"[db] imported {counts}")
    return 0


# --------------------------------------------------------------------------- #
# repo / tools / mine / graph / normalize / source
# --------------------------------------------------------------------------- #
def cmd_repo(cfg: Config, args) -> int:
    from .repositories.manager import RepositoryManager
    rm = RepositoryManager(cfg.data_dir)
    if args.sub == "clone":
        st = rm.clone(args.repo)
        print(f"[repo] {st.slug}: exists={st.exists} head={st.head} commits={st.commit_count} {st.note}")
    elif args.sub == "add":
        rm.register_local(args.name, args.path)
        print(f"[repo] registered local repo '{args.name}' -> {args.path}")
    elif args.sub == "list":
        for entry in rm._registry().items():
            print(f"  {entry[0]}: {entry[1].get('local_path')}")
    return 0


def cmd_tools(cfg: Config, args) -> int:
    from .tools.arcan import ArcanAdapter
    from .tools.designite import DesigniteAdapter
    adapter = {"arcan": ArcanAdapter(), "designite": DesigniteAdapter()}[args.tool]
    findings = adapter.import_findings(Path(args.path))
    out = cfg.data_dir / "raw" / args.tool / f"{args.repo}.json"
    write_json(out, [f.__dict__ for f in findings])
    print(f"[tools] imported {len(findings)} {args.tool} findings -> {out}")
    return 0


def cmd_mine(cfg: Config, args) -> int:
    from .mining.refactoring_miner import RefactoringMinerAdapter
    from .repositories.manager import RepositoryManager
    adapter = RefactoringMinerAdapter()
    rmc = cfg.refactoringminer_config
    if args.sub == "refactorings":
        rm = RepositoryManager(cfg.data_dir)
        out_events = cfg.data_dir / "refactoring_events" / f"{args.repo}.json"
        if rmc.get("mode") == "execute" and rmc.get("executable_path"):
            res = adapter.execute(rm.path_for(args.repo),
                                  cfg.data_dir / "raw" / "refactoringminer" / args.repo,
                                  executable=rmc["executable_path"], limit=args.limit or 0,
                                  log_path=cfg.data_dir / "raw" / "refactoringminer" / f"{args.repo}.log")
            if res.run.status != "ok":
                print(f"[mine] execute status={res.run.status}: {res.run.stderr_tail[:160]}",
                      file=sys.stderr)
            events = res.findings
        else:
            export = cfg.data_dir / "raw" / "refactoringminer" / f"{args.repo}.json"
            events = adapter.import_events(export) if export.exists() else []
            if args.limit:
                events = events[:args.limit]
        write_json(out_events, [e.to_dict() for e in events])
        print(f"[mine] {args.repo}: {len(events)} refactoring events")
    elif args.sub == "batch":
        kind = args.config or "train"
        for entry in load_repo_entries(kind):
            pid = entry["project_id"]
            export = cfg.data_dir / "raw" / "refactoringminer" / f"{pid}.json"
            events = adapter.import_events(export) if export.exists() else []
            write_json(cfg.data_dir / "refactoring_events" / f"{pid}.json",
                       [e.to_dict() for e in events])
            print(f"[mine] {pid}: {len(events)} events")
    return 0


def cmd_graph(cfg: Config, args) -> int:
    from .graphs.builder import DependencyGraphBuilder
    from .memory import ProjectMemory
    edges = read_json(Path(args.edges)) if args.edges else read_json(
        cfg.data_dir / "raw" / "graphs" / f"{args.repo}.json", default=[])
    b = DependencyGraphBuilder()
    dg = b.build(edges or [])
    write_json(cfg.data_dir / "graphs" / f"{args.repo}.json", dg.model_dump())
    ProjectMemory(cfg.data_dir, args.repo).write_json("graph_summary.json", b.summary(dg))
    print(f"[graph] {args.repo}: {dg.graph_metrics.get('node_count')} nodes, "
          f"{dg.graph_metrics.get('cycle_count')} cycles (hash {b.edges_hash(edges or [])[:8]})")
    return 0


def cmd_source(cfg: Config, args) -> int:
    from .source_index.indexer import SourceIndexer
    from .repositories.manager import RepositoryManager
    repo_path = Path(args.path) if args.path else RepositoryManager(cfg.data_dir).path_for(args.repo)
    idx = SourceIndexer().index(args.repo, repo_path)
    write_json(cfg.data_dir / "source_index" / f"{args.repo}.json", idx.to_dict())
    print(f"[source] {args.repo}: {idx.file_count} files, {len(idx.classes)} classes, "
          f"{len(idx.packages)} packages, {len(idx.import_edges)} import edges")
    return 0


def cmd_normalize(cfg: Config, args) -> int:
    from .evidence.normalizer import EvidenceNormalizer
    from .schemas import DependencyGraph, EvidenceCase, SourceIndex
    from .tools.base import ToolFinding
    findings: List[ToolFinding] = []
    for tool in ("arcan", "designite"):
        for rec in read_json(cfg.data_dir / "raw" / tool / f"{args.repo}.json", default=[]) or []:
            findings.append(ToolFinding(**rec))
    dg_data = read_json(cfg.data_dir / "graphs" / f"{args.repo}.json", default={})
    dg = DependencyGraph(**dg_data) if dg_data else DependencyGraph()
    src = read_json(cfg.data_dir / "source_index" / f"{args.repo}.json", default={})
    si = SourceIndex(files=src.get("files", []), classes=src.get("classes", []),
                     methods=src.get("methods", [])) if src else None
    case = EvidenceNormalizer().normalize(args.repo, args.revision or "HEAD", findings, dg, si)
    write_json(cfg.data_dir / "normalized" / f"{args.repo}.json", case.model_dump())
    print(f"[normalize] {args.repo}: {len(case.smells)} smells")
    return 0


# --------------------------------------------------------------------------- #
# dataset / ranker / validate
# --------------------------------------------------------------------------- #
def cmd_dataset(cfg: Config, args) -> int:
    if args.sub == "build-multi-repo":
        from .dataset.multi_repo import build_multi_repo_dataset
        splits = (args.splits or "train").split(",")
        res = build_multi_repo_dataset(cfg, splits)
        print(f"[dataset] multi-repo: {res['train_examples']} train / {res['validation_examples']} val, "
              f"repos={res['stats'].get('by_repository')}, skipped_leakage={res['skipped_leakage']}")
    else:  # build (single/aligned)
        from .dataset.multi_repo import build_multi_repo_dataset
        res = build_multi_repo_dataset(cfg, ["train"])
        print(f"[dataset] {res['train_examples']} examples")
    return 0


def cmd_ranker(cfg: Config, args) -> int:
    from .scripts_support import train_ranker
    ds = Path(args.dataset) if args.dataset else None
    path = train_ranker(cfg, ds, validation_repo=getattr(args, "validation_repo", None))
    report = read_json(cfg.data_dir / "models" / "ranker_report.json", default={})
    m = report.get("metadata", {})
    print(f"[ranker] {m.get('backend')} trained on {m.get('training_example_count')} examples "
          f"({len(m.get('training_repositories', []))} repos), train_score={m.get('train_score')} -> {path}")
    return 0


def cmd_train(cfg: Config, args) -> int:
    # `train ranker` / `train lora` / `train neural` aliases
    if args.sub == "ranker":
        return cmd_ranker(cfg, args)
    if args.sub == "lora":
        return cmd_lora(cfg, args)
    if args.sub == "neural":
        return cmd_neural(cfg, args)
    return 1


def cmd_neural(cfg: Config, args) -> int:
    """Grokking-informed neural ranker: sweep capacity x weight-decay, deploy if it beats GBM."""
    import subprocess
    import sys
    script = Path(__file__).resolve().parent.parent / "scripts" / "sweep_neural_ranker.py"
    return subprocess.call([sys.executable, str(script)])


def cmd_lora(cfg: Config, args) -> int:
    from .training.lora import lora_train
    res = lora_train(cfg, dataset=getattr(args, "dataset", None), dry_run=getattr(args, "dry_run", True))
    print(f"[lora] {res['status']}: {res['message']}")
    return 0 if res["ok"] else 1


def cmd_validate(cfg: Config, args) -> int:
    if args.sub == "leave-one-repo-out":
        from .training.ranker_trainer import RankerTrainer
        ds = Path(args.dataset) if args.dataset else (
            cfg.data_dir / "training" / "multi_repo_train_candidates.jsonl")
        report = RankerTrainer(cfg.data_dir / "models").leave_one_repo_out(ds)
        print(f"[validate] LORO mean_validation_score={report['mean_validation_score']}")
        for f in report["folds"]:
            print(f"   held_out={f['held_out']} val={f['validation_score']} "
                  f"overfit={f['overfitting_warning']}")
    return 0


# --------------------------------------------------------------------------- #
# suggest / recipes / model / evaluate / unseen
# --------------------------------------------------------------------------- #
def cmd_suggest(cfg: Config, args) -> int:
    from .pipeline import InferencePipeline
    from .memory import ProjectMemory
    from .models.manager import resolve_override
    from .export.report import build_report, write_report, write_suggestions
    from .schemas import EvidenceCase
    data = read_json(cfg.data_dir / "normalized" / f"{args.repo}.json")
    if data is None:
        print(f"[suggest] no normalized evidence for {args.repo}; run `normalize` first.",
              file=sys.stderr)
        return 1
    case = EvidenceCase(**data)
    override = resolve_override(cfg, getattr(args, "model", None))
    pipe = InferencePipeline(cfg, top_k_per_smell=args.top_k, model_override=override,
                             min_confidence=getattr(args, "min_confidence", None))
    suggestions, optimisation = pipe.run(case, ProjectMemory(cfg.data_dir, args.repo).memory_ref(case.revision))
    out_dir = cfg.data_dir / "outputs" / args.repo
    write_suggestions(out_dir / "suggestions.json", suggestions)
    report = build_report(case.project_id, case.revision, suggestions, optimisation)
    write_report(out_dir / "report.json", report)
    print(f"[suggest] {args.repo}: {len(suggestions)} suggestions "
          f"(grounding_pass={report['evidence_grounding_pass_rate']}, "
          f"model_calls={optimisation['total_model_calls']}, cache_hits={optimisation['cache_hits']})")
    for s in suggestions[:5]:
        print(f"  #{s.rank} {s.score:.2f} {s.smell_type} -> {s.recommended_refactoring} [{s.verification_status}]")
    return 0


def cmd_recipes(cfg: Config, args) -> int:
    if args.sub == "validate":
        from .openrewrite.validator import RecipeValidator
        from .repositories.manager import RepositoryManager
        repo_path = RepositoryManager(cfg.data_dir).path_for(args.repo)
        rv = RecipeValidator(repo_path, cfg.data_dir / "outputs" / "recipe_logs")
        res = rv.validate_file(cfg.data_dir / "outputs" / args.repo / "suggestions.json")
        print(f"[recipes] validate {args.repo}: {res['status_counts']}")
    return 0


def cmd_model(cfg: Config, args) -> int:
    from .models.manager import list_models, resolve_override, smoke_test
    if args.sub == "list":
        info = list_models(cfg)
        print(f"[model] provider={info['configured_provider']} model={info['configured_model']}")
        print(f"[model] ollama_available={info['ollama_available']} models={info['ollama_models']}")
        print("[model] offline provider always available")
    elif args.sub == "smoke-test":
        res = smoke_test(cfg, resolve_override(cfg, getattr(args, "model", None)))
        print(f"[model] {res['provider']} ({res['model']}) ok={res['ok']} latency={res['latency_s']}s")
        print(f"        response: {res['response_preview']}")
    return 0


def cmd_evaluate(cfg: Config, args) -> int:
    from .schemas import EvidenceCase
    # by-URL or registered-local unseen repo path (addendum §5)
    if getattr(args, "repo_url", None) or (args.name and not getattr(args, "cassandra", None)):
        from .inference.unseen import evaluate_unseen_repo
        from .models.manager import resolve_override
        from .repositories.manager import RepositoryManager
        from .export.report import build_report, write_report, write_suggestions
        name = args.name or "unseen-repo"
        repo_path = None
        if getattr(args, "path", None):
            repo_path = Path(args.path)
        elif not getattr(args, "repo_url", None):
            repo_path = RepositoryManager(cfg.data_dir).path_for(name)
        sugs, report = evaluate_unseen_repo(
            cfg, name, repo_path=repo_path, repo_url=getattr(args, "repo_url", None),
            top_k=args.top_k, model_override=resolve_override(cfg, getattr(args, "model", None)))
        out = cfg.data_dir / "outputs" / name
        write_suggestions(out / "suggestions.json", sugs)
        rep = build_report(name, "HEAD", sugs, report)
        rep["preparation"] = report.get("preparation")
        write_report(out / "report.json", rep)
        print(f"[evaluate] {name}: {len(sugs)} suggestions, prep={report.get('preparation')}")
        return 0

    # cassandra final unseen test (Task 14)
    repo = getattr(args, "cassandra", False) and "apache-cassandra" or (args.repo or "apache-cassandra")
    from .splits.manager import SplitManager, LeakageError
    try:
        SplitManager().assert_no_leakage()
    except LeakageError as e:
        print(f"[evaluate] GUARDRAIL: {e}", file=sys.stderr)
        return 2
    if getattr(args, "dry_run", False):
        sm = SplitManager()
        held_out = sorted(set(sm.unseen) | set(sm.test))
        print(f"[evaluate] DRY-RUN plan for {repo}: normalize -> suggest -> report.")
        print(f"[evaluate] Leakage guard OK. Held out from training: {', '.join(held_out)}")
        print(f"[evaluate] {repo} training-allowed: {sm.is_training_allowed(repo)}")
        return 0
    if getattr(args, "with_normalize", False):
        ns = argparse.Namespace(repo=repo, revision="HEAD")
        if cmd_normalize(cfg, ns):
            return 1
    ns = argparse.Namespace(repo=repo, top_k=args.top_k, model=getattr(args, "model", None))
    rc = cmd_suggest(cfg, ns)
    # attach top-k recall vs history if events present
    from .evaluation.evaluator import Evaluator
    from .mining.refactoring_miner import RefactoringEvent
    hist = [RefactoringEvent(**e) for e in
            (read_json(cfg.data_dir / "refactoring_events" / f"{repo}.json", default=[]) or [])]
    if hist:
        sugs = read_json(cfg.data_dir / "outputs" / repo / "suggestions.json", default=[]) or []
        from .schemas import Suggestion
        recall = Evaluator().topk_recall([Suggestion(**s) for s in sugs], hist, args.top_k)
        rep = read_json(cfg.data_dir / "outputs" / repo / "report.json", default={})
        rep["topk_recall_vs_history"] = recall
        write_json(cfg.data_dir / "outputs" / repo / "report.json", rep)
        print(f"[evaluate] top-{args.top_k} recall vs history: {recall}")
    return rc


# --------------------------------------------------------------------------- #
# generalisation / insights / api / demo / ui
# --------------------------------------------------------------------------- #
def cmd_generalisation(cfg: Config, args) -> int:
    from .reporting.generalisation import build_generalisation_report
    rep = build_generalisation_report(cfg)
    print(f"[generalisation] repos train={len(rep['training_repositories'])} "
          f"unseen={rep['unseen_test_repositories']} "
          f"loro_mean={rep.get('loro_mean_validation_score')}")
    print(f"[generalisation] wrote docs/GENERALISATION_REPORT.md + reports/generalisation_report.{{json,csv}}")
    return 0


def cmd_insights(cfg: Config, args) -> int:
    from .schemas import EvidenceCase
    from . import insights as I
    import json as _json
    case_data = read_json(cfg.data_dir / "normalized" / f"{args.repo}.json")
    sugs = read_json(cfg.data_dir / "outputs" / args.repo / "suggestions.json", default=[]) or []
    kind = args.kind
    if kind == "health" and case_data:
        print(_json.dumps(I.architecture_health_radar(EvidenceCase(**case_data)), indent=2))
    elif kind == "conflicts" and case_data:
        print(_json.dumps(I.evidence_conflict_detector(EvidenceCase(**case_data)), indent=2))
    elif kind == "patterns":
        aligns = read_json(cfg.data_dir / "aligned_examples" / f"{args.repo}.json", default=[]) or []
        print(_json.dumps(I.refactoring_pattern_library(aligns), indent=2))
    elif kind == "active-learning":
        print(_json.dumps(I.active_learning_queue(sugs), indent=2))
    elif kind == "readiness":
        print(_json.dumps(I.repository_readiness_score(sugs), indent=2))
    elif kind == "issue-draft" and sugs:
        print(I.issue_pr_draft(sugs[0]))
    else:
        print(f"[insights] nothing to show for '{kind}' (missing data?)")
    return 0


def cmd_api(cfg: Config, args) -> int:
    if args.sub == "serve":
        try:
            import uvicorn
        except Exception:
            print("[api] uvicorn/fastapi not installed. `pip install fastapi uvicorn`.", file=sys.stderr)
            return 1
        from .api import create_app
        uvicorn.run(create_app(cfg.profile), host="127.0.0.1", port=args.port)
    return 0


def cmd_demo(cfg: Config, args) -> int:
    from .demo import run_local_demo, hpc_demo_plan, hpc_demo_submit
    if args.sub == "full":
        return run_local_demo(cfg)
    if args.sub == "plan":
        return hpc_demo_plan(cfg)
    if args.sub == "submit":
        return hpc_demo_submit(cfg, confirm=getattr(args, "yes", False))
    return 1


def cmd_verify_effect(cfg: Config, args) -> int:
    """Closed loop: for each suggestion, apply the refactoring on a copy and re-measure smells."""
    from .verification.effect_checker import verify_suggestion, snapshot_smells
    from .repositories.manager import RepositoryManager
    repo_path = Path(args.path) if args.path else RepositoryManager(cfg.data_dir).path_for(args.repo)
    if not repo_path.exists():
        print(f"[verify] repo not found at {repo_path}; clone or --path it.", file=sys.stderr)
        return 1
    sug_path = cfg.data_dir / "outputs" / args.repo / "suggestions.json"
    sugs = read_json(sug_path, default=[]) or []
    if not sugs:  # generate first (offline)
        from .inference.unseen import evaluate_unseen_repo
        from .export.report import write_suggestions
        s, _ = evaluate_unseen_repo(cfg, args.repo, repo_path=repo_path,
                                    model_override={"type": "offline"}, top_k=5)
        write_suggestions(sug_path, s)
        sugs = read_json(sug_path, default=[]) or []

    if getattr(args, "appliable_only", False):
        # focus on auto-appliable suggestions (Move Class) so the effect is measurable
        sugs = [s for s in sugs if s.get("recommended_refactoring") == "Move Class"]

    base = snapshot_smells(repo_path, args.repo)
    print(f"[verify] {args.repo}: baseline {base.total} smells, {base.cycle_count} cycles "
          f"({base.node_count} pkgs, {base.edge_count} edges)")

    # Cumulative multi-step: apply the top-N suggestions together, track the cycle trajectory.
    if getattr(args, "cumulative", False):
        from .verification.effect_checker import simulate_cumulative
        cum = simulate_cumulative(base, sugs, max_steps=args.top_k)
        print(f"[verify] CUMULATIVE: applied {cum['steps']} refactorings -> "
              f"packages-in-cycles {cum['packages_in_cycles_before']} -> "
              f"{cum['packages_in_cycles_after']} ({cum['packages_freed']} freed, "
              f"{cum['reduction_pct']}%); largest tangle "
              f"{cum['largest_tangle_before']} -> {cum['largest_tangle_after']} packages")
        for pt in cum["trajectory"]:
            if pt["step"] == 0:
                print(f"   step 0 (baseline): {pt['packages_in_cycles']} pkgs in cycles, "
                      f"largest tangle {pt['largest_tangle']}")
            else:
                print(f"   step {pt['step']:>2} [{pt['refactoring']}] break {pt['edge']}: "
                      f"{pt['packages_in_cycles']} pkgs in cycles (tangle {pt['largest_tangle']})")
        write_json(cfg.data_dir / "outputs" / args.repo / "verify_cumulative.json", cum)
        return 0
    work = cfg.data_dir / "outputs" / args.repo / "verify"
    results = []
    for sug in sugs[: args.top_k]:
        r = verify_suggestion(repo_path, sug, work)
        results.append(r)
        if r.get("applied"):
            mark = "[SMELL REMOVED]" if r.get("smell_removed") else "[no change]"
            how = (f"move {r['break_cycle']['count']} classes ({r['break_cycle']['direction_removed']})"
                   if r.get("break_cycle") else
                   f"{r.get('move', {}).get('class_fqn','')} -> {r.get('move', {}).get('to_package','')}")
            print(f"  [{r['refactoring']} via {r.get('applier')}] {how}: cycles "
                  f"{r['cycles_before']}->{r['cycles_after']}, smells "
                  f"{r['smells_before']}->{r['smells_after']}  {mark}")
        elif r.get("simulated"):
            sim = r.get("simulation", {})
            mark = "[SIMULATED: would remove]" if r.get("smell_removed") else "[SIMULATED: no effect]"
            print(f"  [{r['refactoring']} via graph-simulation] break {sim.get('edge_targeted','')}: "
                  f"cycles {r['cycles_before']}->{r['cycles_after']}  {mark}")
        else:
            print(f"  [{r['refactoring']}] not tested: {r.get('note','')}")
    write_json(cfg.data_dir / "outputs" / args.repo / "verify_effect.json", results)
    removed = sum(1 for r in results if r.get("smell_removed"))
    print(f"[verify] {removed}/{len(results)} suggestions measurably removed a smell. "
          f"-> data/outputs/{args.repo}/verify_effect.json")
    return 0


def cmd_pipeline(cfg: Config, args) -> int:
    """End-to-end on any repo: acquire -> detect -> graph -> suggest -> recipes -> apply -> re-detect."""
    from .e2e import run_pipeline
    from .repositories.manager import slug_to_dirname
    repo_path = Path(args.path) if getattr(args, "path", None) else None
    if getattr(args, "repo_url", None):
        name = args.name or slug_to_dirname(args.repo_url.split("github.com/")[-1].replace(".git", ""))
    else:
        name = args.name or args.repo
    report = run_pipeline(cfg, name, repo_url=getattr(args, "repo_url", None),
                          repo_path=repo_path, top_k=args.top_k)
    print(f"[pipeline] {name} (build: {report.get('build_system')}):")
    for s in report["steps"]:
        print(f"  [{s['step']}] {s['title']} — {s['tool']}\n        {s['summary']}")
    print(f"[pipeline] full report -> data/outputs/{name}/e2e_report.json")
    return 0


def cmd_refactor_openrewrite(cfg: Config, args) -> int:
    """REAL loop: Arcan/Designite detect -> OpenRewrite run (real refactoring) -> re-detect."""
    from .verification.openrewrite_loop import (available_detectors,
                                                refactor_with_openrewrite_and_verify)
    from .repositories.manager import RepositoryManager

    avail = available_detectors()
    detector = getattr(args, "detector", "both")
    if detector in ("arcan", "both") and not avail["arcan"]:
        print("[refactor] Arcan not runnable (need the FULL distribution: jar + lib/).",
              file=sys.stderr)
        if detector == "arcan":
            return 1
        detector = "designite"
    if detector in ("designite", "both") and not avail["designite"]:
        print("[refactor] DesigniteJava.jar not found in tools/.", file=sys.stderr)
        if detector == "designite":
            return 1
        detector = "arcan"

    name = args.repo
    if getattr(args, "repo_url", None):
        # "upload a repo": clone the URL, then run the loop on it.
        name = args.repo or _slug_from_url(args.repo_url)
        mgr = RepositoryManager(cfg.data_dir)
        st = mgr.clone(name, args.repo_url, depth=1)
        repo_path = mgr.path_for(name)
        print(f"[acquire] {args.repo_url} -> {repo_path} ({st.note or 'ok'})")
    elif getattr(args, "path", None):
        repo_path = Path(args.path)
    else:
        repo_path = RepositoryManager(cfg.data_dir).path_for(name)

    # Suggestions are optional now: moves are derived from the detector's own cycle
    # findings, and fall back to suggestions.json only when the tool yields none.
    sugs = read_json(cfg.data_dir / "outputs" / name / "suggestions.json", default=[]) or []
    strategy = getattr(args, "strategy", "merge_package")
    print(f"[refactor] detector={detector} strategy={strategy} repo={name} "
          f"({len(sugs)} prior suggestions)")
    report = refactor_with_openrewrite_and_verify(cfg, name, repo_path, sugs,
                                                  detector=detector, strategy=strategy)
    for s in report["steps"]:
        line = f"  [{s['step']}] {s.get('tool','')}: {s.get('status')}"
        if "smells" in s:
            line += f" — {s.get('smells')} smells {s.get('by_type')}"
            for tool, sub in (s.get("by_tool") or {}).items():
                line += f"\n        {tool}: {sub.get('smells')} {sub.get('by_type')}"
        elif s["step"] == "plan_refactorings":
            line += (f" — {s.get('plans_applicable')} applicable plans over "
                     f"{s.get('smell_types_actionable')}/{s.get('smell_types_detected')} smell "
                     f"types, {s.get('recipe_operations')} recipe operations")
            for smell, n in (s.get("by_smell_type") or {}).items():
                line += f"\n        {smell}: {n} plan(s)"
            skipped = [p for p in (s.get("plans") or []) if not p.get("applicable")]
            by_reason = {}
            for p in skipped:
                by_reason.setdefault(p["smell_type"], p.get("reason", ""))
            if by_reason:
                line += f"\n        -- not automatable ({len(skipped)} findings) --"
                for smell, why in list(by_reason.items())[:8]:
                    line += f"\n        {smell}: {why[:88]}"
        elif s["step"] == "plan_moves":
            line += f" — {s.get('count')} class moves (from {s.get('derived_from')})"
        elif s["step"] == "openrewrite":
            if s.get("status") == "skipped":
                line += f" — {s.get('note')}"
                d = s.get("diagnosis") or {}
                if d:
                    line += (f"\n        cycles: {d.get('cross_package_cycles')} cross-package, "
                             f"{d.get('intra_package_cycles')} intra-package")
                    for b in (d.get("blocked_merges") or [])[:3]:
                        line += f"\n        blocked: {b}"
            else:
                line += f" — changed {s.get('changed_count', 0)} files ({s.get('mvn','')})"
        elif s["step"] == "compare":
            if s.get("verification_status") == "verified":
                line += f" — removed {s.get('removed')} smells, delta {s.get('delta_by_type')}"
            else:
                line += f" — UNVERIFIED: {s.get('note')}"
            for tool, sub in (s.get("per_tool") or {}).items():
                if sub.get("measured"):
                    line += (f"\n        {tool}: {sub['before']} -> {sub['after']} "
                             f"({sub['removed']:+d})")
                else:
                    line += f"\n        {tool}: {sub['before']} -> UNMEASURABLE ({sub.get('note')})"
        print(line)
    if report.get("verification_status") == "unverified_build_broken":
        print(f"[refactor] WARNING: the refactored code did not build "
              f"({report.get('build_after_refactoring')}); the after-state is NOT measured.",
              file=sys.stderr)
    print(f"[refactor] -> data/outputs/{name}/openrewrite_loop_report.json")
    return 0


def _slug_from_url(url: str) -> str:
    """github.com/apache/commons-text.git -> apache-commons-text"""
    parts = [p for p in url.rstrip("/").replace(".git", "").split("/") if p]
    return "-".join(parts[-2:]).lower() if len(parts) >= 2 else parts[-1].lower()


def cmd_ui(cfg: Config, args) -> int:
    import subprocess
    app = Path(__file__).resolve().parent.parent / "ui" / "streamlit_app.py"
    print("[ui] launching Streamlit ...")
    return subprocess.call(["streamlit", "run", str(app)])


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def build_parser(default_profile: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dsarp", description="DSARP Evidence-Based Refactoring Agent")
    p.add_argument("--profile", default=default_profile)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("setup").set_defaults(func=cmd_setup)

    d = sub.add_parser("db"); ds = d.add_subparsers(dest="sub", required=True)
    for name in ("init", "status", "import-outputs"):
        ds.add_parser(name).set_defaults(func=cmd_db)

    r = sub.add_parser("repo"); rs = r.add_subparsers(dest="sub", required=True)
    rc = rs.add_parser("clone"); rc.add_argument("--repo", required=True); rc.set_defaults(func=cmd_repo)
    ra = rs.add_parser("add"); ra.add_argument("--name", required=True); ra.add_argument("--path", required=True); ra.set_defaults(func=cmd_repo)
    rs.add_parser("list").set_defaults(func=cmd_repo)

    t = sub.add_parser("tools"); tsx = t.add_subparsers(dest="sub", required=True)
    ti = tsx.add_parser("import"); ti.add_argument("--repo", required=True)
    ti.add_argument("--tool", required=True, choices=["arcan", "designite"])
    ti.add_argument("--path", required=True); ti.set_defaults(func=cmd_tools)

    mi = sub.add_parser("mine"); mis = mi.add_subparsers(dest="sub", required=True)
    mr = mis.add_parser("refactorings"); mr.add_argument("--repo", required=True)
    mr.add_argument("--limit", type=int, default=0); mr.set_defaults(func=cmd_mine)
    mb = mis.add_parser("batch"); mb.add_argument("--config", default="train"); mb.set_defaults(func=cmd_mine)

    g = sub.add_parser("graph"); gs = g.add_subparsers(dest="sub", required=True)
    gb = gs.add_parser("build"); gb.add_argument("--repo", required=True); gb.add_argument("--edges")
    gb.set_defaults(func=cmd_graph)

    sc = sub.add_parser("source"); scs = sc.add_subparsers(dest="sub", required=True)
    si = scs.add_parser("index"); si.add_argument("--repo", required=True); si.add_argument("--path")
    si.set_defaults(func=cmd_source)

    nz = sub.add_parser("normalize"); nz.add_argument("--repo", required=True)
    nz.add_argument("--revision", default="HEAD"); nz.set_defaults(func=cmd_normalize)

    da = sub.add_parser("dataset"); das = da.add_subparsers(dest="sub", required=True)
    das.add_parser("build").set_defaults(func=cmd_dataset)
    dbm = das.add_parser("build-multi-repo"); dbm.add_argument("--splits", default="train")
    dbm.set_defaults(func=cmd_dataset)

    rk = sub.add_parser("ranker"); rks = rk.add_subparsers(dest="sub", required=True)
    rt = rks.add_parser("train"); rt.add_argument("--dataset"); rt.add_argument("--validation-repo", dest="validation_repo")
    rt.set_defaults(func=cmd_ranker)

    tr = sub.add_parser("train"); trs = tr.add_subparsers(dest="sub", required=True)
    trr = trs.add_parser("ranker"); trr.add_argument("--dataset"); trr.add_argument("--validation-repo", dest="validation_repo"); trr.set_defaults(func=cmd_train)
    trl = trs.add_parser("lora"); trl.add_argument("--dataset"); trl.add_argument("--dry-run", action="store_true", dest="dry_run"); trl.set_defaults(func=cmd_train)
    trn = trs.add_parser("neural"); trn.set_defaults(func=cmd_train)  # grokking neural ranker

    va = sub.add_parser("validate"); vas = va.add_subparsers(dest="sub", required=True)
    vl = vas.add_parser("leave-one-repo-out"); vl.add_argument("--dataset"); vl.set_defaults(func=cmd_validate)

    sg = sub.add_parser("suggest"); sg.add_argument("--repo", required=True)
    sg.add_argument("--top-k", type=int, default=3); sg.add_argument("--model")
    sg.add_argument("--min-confidence", type=float, dest="min_confidence")
    sg.set_defaults(func=cmd_suggest)

    re = sub.add_parser("recipes"); res = re.add_subparsers(dest="sub", required=True)
    rev = res.add_parser("validate"); rev.add_argument("--repo", required=True); rev.set_defaults(func=cmd_recipes)

    mo = sub.add_parser("model"); mos = mo.add_subparsers(dest="sub", required=True)
    mos.add_parser("list").set_defaults(func=cmd_model)
    mst = mos.add_parser("smoke-test"); mst.add_argument("--model"); mst.set_defaults(func=cmd_model)

    ev = sub.add_parser("evaluate")
    ev.add_argument("cassandra", nargs="?", default=None)
    ev.add_argument("--repo", default=None); ev.add_argument("--repo-url", dest="repo_url")
    ev.add_argument("--name"); ev.add_argument("--path"); ev.add_argument("--revision", default="HEAD")
    ev.add_argument("--with-normalize", action="store_true", dest="with_normalize")
    ev.add_argument("--dry-run", action="store_true", dest="dry_run")
    ev.add_argument("--model"); ev.add_argument("--top-k", type=int, default=3)
    ev.set_defaults(func=cmd_evaluate)

    gen = sub.add_parser("generalisation"); gens = gen.add_subparsers(dest="sub", required=True)
    gens.add_parser("report").set_defaults(func=cmd_generalisation)

    ins = sub.add_parser("insights"); ins.add_argument("kind",
        choices=["health", "conflicts", "patterns", "active-learning", "readiness", "issue-draft"])
    ins.add_argument("--repo", required=True); ins.set_defaults(func=cmd_insights)

    ap = sub.add_parser("api"); aps = ap.add_subparsers(dest="sub", required=True)
    apv = aps.add_parser("serve"); apv.add_argument("--port", type=int, default=8000); apv.set_defaults(func=cmd_api)

    dm = sub.add_parser("demo"); dms = dm.add_subparsers(dest="sub", required=True)
    dms.add_parser("full").set_defaults(func=cmd_demo)
    dms.add_parser("plan").set_defaults(func=cmd_demo)
    dsub = dms.add_parser("submit"); dsub.add_argument("--yes", action="store_true"); dsub.set_defaults(func=cmd_demo)

    ve = sub.add_parser("verify-effect")
    ve.add_argument("--repo", required=True); ve.add_argument("--path")
    ve.add_argument("--top-k", type=int, default=5)
    ve.add_argument("--appliable-only", action="store_true", dest="appliable_only",
                    help="only test auto-appliable (Move Class) suggestions")
    ve.add_argument("--cumulative", action="store_true",
                    help="apply top-N suggestions together; report the cycle-reduction trajectory")
    ve.set_defaults(func=cmd_verify_effect)

    pl = sub.add_parser("pipeline")  # end-to-end on any repo
    pl.add_argument("--repo"); pl.add_argument("--repo-url", dest="repo_url")
    pl.add_argument("--name"); pl.add_argument("--path")
    pl.add_argument("--top-k", type=int, default=8); pl.set_defaults(func=cmd_pipeline)

    ro = sub.add_parser("refactor-openrewrite")  # detect -> OpenRewrite run -> re-detect
    ro.add_argument("--repo"); ro.add_argument("--path")
    ro.add_argument("--repo-url", dest="repo_url",
                    help="git URL to clone and analyse (any repo)")
    ro.add_argument("--detector", choices=("arcan", "designite", "both"), default="both",
                    help="real smell tool used BEFORE and AFTER the refactoring")
    ro.add_argument("--strategy", choices=("merge_package", "move_classes"),
                    default="merge_package",
                    help="merge_package: ChangePackage, relocates whole packages (compile-safe); "
                         "move_classes: ChangeType, surgical but can break same-package refs")
    ro.set_defaults(func=cmd_refactor_openrewrite)

    sub.add_parser("ui").set_defaults(func=cmd_ui)
    return p


def _run(argv: Optional[List[str]], default_profile: str) -> int:
    parser = build_parser(default_profile)
    args = parser.parse_args(argv)
    cfg = load_config(args.profile)
    if args.command != "setup":
        args._quiet = True
        cmd_setup(cfg, args)  # ensure dirs
    return args.func(cfg, args)


def main(argv: Optional[List[str]] = None) -> int:
    return _run(argv, "local")


def local_main(argv: Optional[List[str]] = None) -> int:
    return _run(argv, "local")


def hpc_main(argv: Optional[List[str]] = None) -> int:
    return _run(argv, "hpc")


if __name__ == "__main__":
    raise SystemExit(main())
