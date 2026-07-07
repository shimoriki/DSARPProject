"""`dsarp` command-line interface (Typer)."""
from __future__ import annotations

import json
from typing import Optional

import typer

from . import services

cli = typer.Typer(help="DSARP Refactoring Suggestion Studio", no_args_is_help=True)
project_app = typer.Typer(help="Manage projects", no_args_is_help=True)
evidence_app = typer.Typer(help="Build and split normalized evidence", no_args_is_help=True)
suggest_app = typer.Typer(help="Run suggestion agents", no_args_is_help=True)
review_app = typer.Typer(help="Review data", no_args_is_help=True)
skill_app = typer.Typer(help="Skill optimization", no_args_is_help=True)
dataset_app = typer.Typer(help="Dataset export", no_args_is_help=True)
experiment_app = typer.Typer(help="Experiments and comparisons", no_args_is_help=True)
cli.add_typer(project_app, name="project")
cli.add_typer(evidence_app, name="evidence")
cli.add_typer(suggest_app, name="suggest")
cli.add_typer(review_app, name="review")
cli.add_typer(skill_app, name="skill")
cli.add_typer(dataset_app, name="dataset")
cli.add_typer(experiment_app, name="experiment")


def _ctx() -> services.AppContext:
    return services.init_context()


def _emit(data) -> None:
    typer.echo(json.dumps(data, indent=2, default=str))


@project_app.command("add")
def project_add(name: str = typer.Option(...), path: str = typer.Option(""),
                architecture: str = typer.Option("package-based-java"),
                component_type: str = typer.Option("package"),
                revision: Optional[str] = typer.Option(None)):
    _emit(services.add_project(_ctx(), name, path, architecture, component_type, revision))


@project_app.command("list")
def project_list():
    _emit(_ctx().store.list_projects())


@cli.command("analyze")
def analyze(project: str = typer.Option(...),
            tools: str = typer.Option(..., help="comma-separated: arcan,designite")):
    _emit(services.analyze_project(_ctx(), project, [t.strip() for t in tools.split(",")]))


@cli.command("import")
def import_(project: str = typer.Option(...), tool: str = typer.Option(...),
            path: str = typer.Option(...)):
    _emit(services.import_tool_file(_ctx(), project, tool, path))


@evidence_app.command("build")
def evidence_build(project: str = typer.Option(...)):
    _emit({"cases": services.rebuild_evidence(_ctx(), project)})


@evidence_app.command("split")
def evidence_split(project: Optional[str] = typer.Option(None)):
    _emit(services.split_evidence(_ctx(), project))


@evidence_app.command("list")
def evidence_list(project: str = typer.Option(...),
                  split: Optional[str] = typer.Option(None)):
    _emit(_ctx().store.list_cases(project_id=project, split=split))


@suggest_app.command("run")
def suggest_run(project: str = typer.Option(...),
                agent: str = typer.Option("tool_evidence",
                                          help="baseline | skill | tool_evidence"),
                model: Optional[str] = typer.Option(None, help="model id override"),
                provider: Optional[str] = typer.Option(None),
                skill: Optional[str] = typer.Option(None),
                skill_version: Optional[str] = typer.Option(None),
                split: Optional[str] = typer.Option(None),
                critic: bool = typer.Option(False, "--critic")):
    runs = services.run_agents(_ctx(), project, agent, provider_name=provider,
                               model_id=model, skill_name=skill,
                               skill_version=skill_version, split=split,
                               with_critic=critic or None)
    _emit([{k: r[k] for k in ("run_id", "smell_id", "agent_mode", "model_id",
                              "skill_version", "status", "total_tokens",
                              "runtime_seconds")} for r in runs])


@suggest_app.command("rescore")
def suggest_rescore(project: str = typer.Option(...)):
    """Recompute structural checks and suggested scores for stored runs."""
    _emit({"rescored": services.rescore_runs(_ctx(), project)})


@review_app.command("export")
def review_export(project: Optional[str] = typer.Option(None)):
    _emit(_ctx().store.list_reviews(project_id=project))


@skill_app.command("list")
def skill_list():
    _emit(_ctx().store.list_skills())


@skill_app.command("optimize")
def skill_optimize(skill: str = typer.Option(..., help="e.g. BreakCyclicDependencySkill_v0"),
                   provider: Optional[str] = typer.Option(None),
                   model: Optional[str] = typer.Option(None)):
    if "_v" in skill:
        name, _, version = skill.rpartition("_v")
        version = "v" + version
    else:
        raise typer.BadParameter("expected <SkillName>_v<N>")
    _emit(services.optimize(_ctx(), name, version, provider, model))


@cli.command("validate")
def validate(project: str = typer.Option(...),
             skill: str = typer.Option("BreakCyclicDependencySkill"),
             skill_v0: str = typer.Option(..., "--skill-v0"),
             skill_v1: str = typer.Option(..., "--skill-v1"),
             provider: Optional[str] = typer.Option(None),
             model: Optional[str] = typer.Option(None)):
    _emit(services.validate(_ctx(), project, skill, skill_v0, skill_v1, provider, model))


@cli.command("promote")
def promote(report_id: str = typer.Option(...),
            approver: Optional[str] = typer.Option(None)):
    """Record human approval for a passed validation report and promote."""
    _emit(services.approve_and_promote(_ctx(), report_id, approver))


@dataset_app.command("export")
def dataset_export(min_hgrs: float = typer.Option(4.0, "--min-hgrs"),
                   project: Optional[str] = typer.Option(None),
                   lora_prep: bool = typer.Option(False, "--lora-prep")):
    _emit(services.export_dataset(_ctx(), min_hgrs, project, lora_prep=lora_prep))


@experiment_app.command("run")
def experiment_run(name: str = typer.Option(...), project: str = typer.Option(...),
                   modes: str = typer.Option("baseline,skill,tool_evidence"),
                   models: str = typer.Option(None, help="comma-separated model ids"),
                   split: Optional[str] = typer.Option(None)):
    ctx = _ctx()
    model_specs = ([{"model_id": m.strip()} for m in models.split(",")]
                   if models else [{"model_id": ctx.cfg.model.model_id}])
    _emit(services.run_experiment(ctx, name, project,
                                  [m.strip() for m in modes.split(",")],
                                  model_specs, split=split))


@experiment_app.command("compare")
def experiment_compare(project: Optional[str] = typer.Option(None),
                       experiment_id: Optional[str] = typer.Option(None)):
    _emit(services.comparison_table(_ctx(), project, experiment_id))


@cli.command("doctor")
def doctor(provider: Optional[str] = typer.Option(None),
           model: Optional[str] = typer.Option(None)):
    """Check that the configured local model endpoint is reachable."""
    _emit(services.check_model_endpoint(_ctx(), provider, model))


@cli.command("serve-api")
def serve_api(port: int = typer.Option(8600), host: str = typer.Option("127.0.0.1")):
    import uvicorn
    uvicorn.run("dsarp.api:app", host=host, port=port)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
