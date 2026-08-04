"""Tasks 18-19 — end-to-end demo drivers.

`demo full` runs the whole LOCAL MVP on sample/fixture data without proprietary tools
or cloud. `demo plan` prints the HPC plan (submits nothing); `demo submit --yes` submits
Slurm jobs only when confirmed AND sbatch exists.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict

from .config import Config, load_repo_entries


def _stage_sample_data(cfg: Config) -> None:
    """Stage the single-repo Cassandra sample + multi-repo fixtures via real adapters."""
    import sys
    scripts = Path(__file__).resolve().parent.parent / "scripts"
    for script in ("make_sample_data.py", "make_multi_repo_fixtures.py"):
        subprocess.run([sys.executable, str(scripts / script)], check=False)


def run_local_demo(cfg: Config) -> int:
    from .dataset.multi_repo import build_multi_repo_dataset
    from .scripts_support import train_ranker
    from .reporting.generalisation import build_generalisation_report
    from .pipeline import InferencePipeline
    from .memory import ProjectMemory
    from .export.report import build_report, write_report, write_suggestions
    from .schemas import EvidenceCase
    from .openrewrite.validator import RecipeValidator
    from .util import read_json

    print("=" * 64)
    print("DSARP LOCAL DEMO — offline, no proprietary tools, no cloud")
    print("=" * 64)

    print("\n[1/9] staging sample data + multi-repo fixtures ...")
    _stage_sample_data(cfg)

    print("[2/9] normalising Cassandra evidence (unseen test repo) ...")
    from .cli import cmd_normalize
    import argparse
    cmd_normalize(cfg, argparse.Namespace(repo="apache-cassandra", revision="HEAD"))

    print("[3/9] building multi-repository dataset (train split) ...")
    ds = build_multi_repo_dataset(cfg, ["train"])
    print(f"       -> {ds['train_examples']} examples across {ds['stats'].get('repositories')} repos")

    print("[4/9] training preference ranker (repo-independent features) ...")
    # Don't clobber a better real model (e.g. the deployed grokking neural ranker) with the
    # fixture GBM. Only (re)train on fixtures if no stronger real ranker is already deployed.
    from .util import read_json as _rj
    _meta = (_rj(cfg.data_dir / "models" / "ranker_report.json", default={}) or {}).get("metadata", {})
    if _meta.get("backend", "").startswith("neural") or _meta.get("training_example_count", 0) > 1000:
        print(f"       -> keeping deployed real ranker ({_meta.get('backend')}, "
              f"{_meta.get('training_example_count')} examples, LORO {_meta.get('validation_score')})")
    else:
        train_ranker(cfg, cfg.data_dir / "training" / "multi_repo_train_candidates.jsonl")

    print("[5/9] leave-one-repository-out validation ...")
    from .training.ranker_trainer import RankerTrainer
    loro = RankerTrainer(cfg.data_dir / "models").leave_one_repo_out(
        cfg.data_dir / "training" / "multi_repo_train_candidates.jsonl")
    print(f"       -> mean LORO validation score = {loro['mean_validation_score']}")

    print("[6/9] generating ranked suggestions for Cassandra (offline/Ollama) ...")
    case = EvidenceCase(**read_json(cfg.data_dir / "normalized" / "apache-cassandra.json"))
    pipe = InferencePipeline(cfg, top_k_per_smell=3)
    sugs, opt = pipe.run(case, ProjectMemory(cfg.data_dir, "apache-cassandra").memory_ref(case.revision))
    out = cfg.data_dir / "outputs" / "apache-cassandra"
    write_suggestions(out / "suggestions.json", sugs)
    report = build_report(case.project_id, case.revision, sugs, opt)
    write_report(out / "report.json", report)
    print(f"       -> {len(sugs)} suggestions, grounding_pass={report['evidence_grounding_pass_rate']}, "
          f"hallucinations={report['hallucination_failure_count']}, cache_hits={opt['cache_hits']}")

    print("[7/9] validating OpenRewrite recipe drafts (marks draft unless build passes) ...")
    RecipeValidator(None, out / "recipe_logs").validate_file(out / "suggestions.json")

    print("[8/9] building generalisation report ...")
    build_generalisation_report(cfg)

    print("[9/9] token optimisation report ...")
    print(f"       -> model_calls={opt['total_model_calls']} cache_hits={opt['cache_hits']} "
          f"est_tokens_saved={opt['estimated_tokens_saved']}")

    print("\nDEMO COMPLETE. Browse results with: dsarp-local ui")
    print(f"Outputs: {out}\\suggestions.json, report.json ; docs/GENERALISATION_REPORT.md")
    return 0


def hpc_demo_plan(cfg: Config) -> int:
    slurm = Path(__file__).resolve().parent.parent / "slurm"
    scripts = sorted(p.name for p in slurm.glob("*.slurm")) if slurm.exists() else []
    train = [e["project_id"] for e in load_repo_entries("train")]
    print("=" * 64)
    print("DSARP HPC DEMO PLAN (nothing is submitted)")
    print("=" * 64)
    print(f"Profile           : {cfg.profile}")
    print(f"Train repos ({len(train)})   : {', '.join(train)}")
    print(f"Validation        : {[e['project_id'] for e in load_repo_entries('validation')]}")
    print(f"Unseen test       : {[e['project_id'] for e in load_repo_entries('unseen')]}")
    print(f"Data dir          : {cfg.data_dir}")
    print(f"Model (vLLM)      : {cfg.model_provider.get('model')}")
    print(f"Slurm scripts     : {scripts}")
    print("Expected outputs  : data/training/*.jsonl, data/models/ranker.pkl, "
          "data/outputs/apache-cassandra/*, data/reports/generalisation_report.*")
    print("GPU needs         : 1-4 GPUs for vLLM serving; LoRA optional (2 GPUs).")
    print("\nTo submit (guarded): dsarp-hpc demo submit --yes")
    return 0


def hpc_demo_submit(cfg: Config, confirm: bool = False) -> int:
    if not confirm:
        print("[demo] refusing to submit without --yes (prevents accidental large jobs).")
        return 1
    if shutil.which("sbatch") is None:
        print("[demo] sbatch not found — not on a Slurm cluster. Plan only.")
        return 1
    slurm = Path(__file__).resolve().parent.parent / "slurm"
    order = ["mine_all_repos.slurm", "build_dataset.slurm", "train_ranker.slurm",
             "serve_vllm.slurm", "evaluate_cassandra.slurm"]
    for name in order:
        script = slurm / name
        if script.exists():
            print(f"[demo] sbatch {script}")
            subprocess.run(["sbatch", str(script)], check=False)
    return 0
