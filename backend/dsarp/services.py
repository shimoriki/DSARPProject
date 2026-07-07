"""Orchestration layer shared by the CLI, the FastAPI app, and the Streamlit UI."""
from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .adapters import get_adapter
from .agents.critic import run_critic
from .agents.runner import run_suggestion
from .config import AppConfig, ModelConfig, load_config
from .hgrs import CRITERIA, compute_hgrs
from .log import get_logger
from .models.review import Decision, HumanReview, WouldTry
from .models.suggestion import AgentMode
from .normalize import build_evidence
from .providers.base import ModelProvider, make_provider
from .skillopt.digest import build_digest
from .skillopt.optimizer import optimize_skill
from .skillopt.splits import assign_splits
from .skillopt.validate import promote_candidate, validate_skills
from .store.db import Database
from .store.repos import Store
from . import exports as exports_mod

log = get_logger("services")

DEFAULT_SKILL_NAME = "BreakCyclicDependencySkill"
SKILL_BY_SMELL = {"cyclic_dependency": DEFAULT_SKILL_NAME}


@dataclass
class AppContext:
    cfg: AppConfig
    store: Store

    def provider(self, provider_name: str | None = None,
                 model_id: str | None = None) -> ModelProvider:
        mc = self.cfg.model.model_copy()
        if provider_name:
            mc.provider = provider_name
        if model_id:
            mc.model_id = model_id
        return make_provider(mc)

    def critic_provider(self) -> Optional[ModelProvider]:
        if not self.cfg.critic.enabled:
            return None
        mc = self.cfg.model.model_copy()
        if self.cfg.critic.provider:
            mc.provider = self.cfg.critic.provider
        if self.cfg.critic.model_id:
            mc.model_id = self.cfg.critic.model_id
        return make_provider(mc)


def init_context(config_path: str | None = None,
                 root_dir: str | Path | None = None) -> AppContext:
    cfg = load_config(config_path, root_dir)
    db = Database(cfg.database_path)
    ctx = AppContext(cfg=cfg, store=Store(db))
    ensure_default_skills(ctx)
    return ctx


def ensure_default_skills(ctx: AppContext) -> None:
    """Register skill files found in skills_dir that are not in the DB yet."""
    skills_dir = ctx.cfg.skills_path
    if not skills_dir.exists():
        return
    for path in sorted(skills_dir.glob("*.md")):
        stem = path.stem
        if "_candidate" in stem:
            continue
        if "_v" in stem:
            name, _, version = stem.rpartition("_v")
            version = "v" + version
        else:
            name, version = stem, "v0"
        if not ctx.store.get_skill(name, version):
            rel = str(Path(ctx.cfg.skills_dir) / path.name)
            has_production = ctx.store.production_skill(name) is not None
            ctx.store.register_skill(
                name, version, rel,
                status="archived" if has_production else "production")


# ---------------- projects, import, analyze, evidence ----------------

def add_project(ctx: AppContext, name: str, path: str = "",
                architecture_type: str = "package-based-java",
                component_type: str = "package",
                source_revision: str | None = None) -> dict:
    return ctx.store.add_project(name, path, architecture_type,
                                 component_type, source_revision)


def import_tool_file(ctx: AppContext, project_name: str, tool: str,
                     file_path: str) -> dict:
    project = ctx.store.get_project(project_name)
    if not project:
        raise ValueError(f"unknown project '{project_name}'")
    path = ctx.cfg.resolve(file_path)
    if not path.exists():
        raise FileNotFoundError(f"import file not found: {path}")

    adapter = get_adapter(tool)
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    run_id = ctx.store.create_tool_run(
        project["id"], tool, "import", source_path=str(path),
        source_hash=source_hash)
    try:
        result = adapter.parse_import(path)
    except Exception as exc:
        ctx.store.finish_tool_run(run_id, "error", str(exc))
        raise

    smell_records = [{
        "kind": "smell", "tool_record_id": s.tool_record_id,
        "raw_source_file": s.raw_source_file, "smell_type_raw": s.smell_type_raw,
        "affected_components": s.affected_components, "attributes": s.attributes,
    } for s in result.smells]
    edge_records = [{
        "kind": "edge", "tool_record_id": f"{e.from_component}->{e.to_component}",
        "raw_source_file": e.raw_source_file, "from": e.from_component,
        "to": e.to_component, "weight": e.weight,
    } for e in result.edges]
    metric_records = [{
        "kind": "metric", "tool_record_id": f"{m.component}:{m.name}",
        "raw_source_file": m.raw_source_file, "component": m.component,
        "name": m.name, "value": m.value,
    } for m in result.metrics]
    ctx.store.add_raw_findings(run_id, tool, smell_records + edge_records + metric_records)

    existing = len(ctx.store.edges_for_project(project["id"]))
    edges_payload = []
    for i, e in enumerate(result.edges, start=existing + 1):
        edges_payload.append({
            "from": e.from_component, "to": e.to_component,
            "relation_type": e.relation_type,
            "evidence_id": f"{tool.upper()}_EDGE_{i:03d}",
            "confidence": e.confidence, "source": tool,
        })
    if edges_payload:
        ctx.store.add_edges(project["id"], run_id, edges_payload)

    ctx.store.finish_tool_run(run_id, "ok")
    summary = {"tool_run_id": run_id, "tool": tool, "file": str(path),
               "smells": len(result.smells), "edges": len(result.edges),
               "metrics": len(result.metrics)}
    log.info("imported %s: %s", path.name, summary)
    return summary


def analyze_project(ctx: AppContext, project_name: str, tools: list[str]) -> list[dict]:
    """Execute-mode: run configured local tools, then import their outputs.

    DSARP does not ship tool binaries and assumes you hold valid licenses for
    Arcan/Designite; commands come from config/tools.
    """
    project = ctx.store.get_project(project_name)
    if not project:
        raise ValueError(f"unknown project '{project_name}'")
    results = []
    for tool in tools:
        tool_cfg = ctx.cfg.tools.get(tool)
        if not tool_cfg:
            raise ValueError(f"no execution command configured for tool '{tool}'")
        adapter = get_adapter(tool)
        out_dir = ctx.cfg.data_path / "raw_imports" / project["name"] / tool / \
            datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_dir.mkdir(parents=True, exist_ok=True)
        command = adapter.build_command(dict(tool_cfg), project["path"], str(out_dir))
        run_id = ctx.store.create_tool_run(project["id"], tool, "execute",
                                           command=command, source_path=str(out_dir))
        log.info("executing %s: %s", tool, command)
        try:
            proc = subprocess.run(shlex.split(command), capture_output=True,
                                  text=True, timeout=3600)
            if proc.returncode != 0:
                raise RuntimeError(
                    f"{tool} exited with {proc.returncode}: {proc.stderr[:2000]}")
        except Exception as exc:
            ctx.store.finish_tool_run(run_id, "error", str(exc))
            results.append({"tool": tool, "status": "error", "error": str(exc)})
            continue
        ctx.store.finish_tool_run(run_id, "ok")
        imported = []
        for f in adapter.output_files(out_dir):
            try:
                imported.append(import_tool_file(ctx, project_name, tool, str(f)))
            except Exception as exc:  # keep going; record the failure
                imported.append({"file": str(f), "status": "error", "error": str(exc)})
        results.append({"tool": tool, "status": "ok", "command": command,
                        "imported": imported})
    return results


def rebuild_evidence(ctx: AppContext, project_name: str) -> int:
    cases = build_evidence(ctx.store, ctx.cfg, project_name)
    return len(cases)


def split_evidence(ctx: AppContext, project_name: str | None = None) -> dict:
    return assign_splits(ctx.store, ctx.cfg, project_name)


# ---------------- suggestions ----------------

def check_model_endpoint(ctx: AppContext, provider_name: str | None = None,
                         model_id: str | None = None) -> dict:
    """Preflight: is the configured model endpoint reachable and the model there?"""
    import httpx

    mc = ctx.cfg.model.model_copy()
    if provider_name:
        mc.provider = provider_name
    if model_id:
        mc.model_id = model_id
    provider = (mc.provider or "mock").lower()
    if provider == "mock":
        return {"ok": True, "provider": "mock", "model_id": mc.model_id,
                "message": "mock provider is always available (offline)"}
    base = mc.base_url.rstrip("/")
    try:
        if provider == "ollama":
            resp = httpx.get(f"{base}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            if not any(m == mc.model_id or m.split(":")[0] == mc.model_id
                       for m in models):
                return {"ok": False, "provider": provider, "model_id": mc.model_id,
                        "message": f"Ollama is running but model '{mc.model_id}' is "
                                   f"not pulled. Available: {models or 'none'}. "
                                   f"Run: ollama pull {mc.model_id}"}
        else:
            url = base + ("/models" if base.endswith("/v1") else "/v1/models")
            headers = {"Authorization": f"Bearer {mc.api_key}"} if mc.api_key else {}
            httpx.get(url, headers=headers, timeout=5).raise_for_status()
    except httpx.HTTPError as exc:
        return {"ok": False, "provider": provider, "model_id": mc.model_id,
                "message": f"Model endpoint not reachable at {base} ({exc.__class__.__name__}). "
                           "Start your local server (e.g. 'ollama serve', vLLM, "
                           "llama.cpp) or use provider 'mock' to work offline."}
    return {"ok": True, "provider": provider, "model_id": mc.model_id,
            "message": f"endpoint at {base} is reachable and model is available"}


def resolve_skill(ctx: AppContext, smell_key: str,
                  skill_name: str | None = None,
                  skill_version: str | None = None) -> tuple[str | None, str | None, str | None]:
    """Return (name, version, text) for the skill to use, or (None, None, None)."""
    name = skill_name or SKILL_BY_SMELL.get(smell_key)
    if not name:
        return None, None, None
    if skill_version:
        row = ctx.store.get_skill(name, skill_version)
    else:
        row = ctx.store.production_skill(name)
    if not row:
        return None, None, None
    text = ctx.cfg.resolve(row["file_path"]).read_text(encoding="utf-8")
    return name, row["version"], text


def run_agents(ctx: AppContext, project_name: str, agent_mode: str,
               case_ids: list[str] | None = None,
               provider_name: str | None = None, model_id: str | None = None,
               skill_name: str | None = None, skill_version: str | None = None,
               split: str | None = None, with_critic: bool | None = None,
               experiment_id: str | None = None) -> list[dict]:
    mode = AgentMode(agent_mode)
    health = check_model_endpoint(ctx, provider_name, model_id)
    if not health["ok"]:
        raise RuntimeError(health["message"])
    provider = ctx.provider(provider_name, model_id)
    rows = ctx.store.list_cases(project_id=project_name, split=split)
    if case_ids:
        rows = [r for r in rows if r["id"] in set(case_ids)]
    if not rows:
        raise ValueError("no evidence cases matched; build evidence first")

    critic_provider = ctx.critic_provider() if (
        with_critic if with_critic is not None else ctx.cfg.critic.enabled) else None

    runs = []
    for row in rows:
        case = ctx.store.get_case(row["id"])
        s_name = s_version = s_text = None
        if mode != AgentMode.baseline:
            s_name, s_version, s_text = resolve_skill(
                ctx, case.smell_key, skill_name, skill_version)
        run = run_suggestion(ctx.cfg, ctx.store, provider, case, mode,
                             skill_name=s_name, skill_version=s_version,
                             skill_text=s_text, experiment_id=experiment_id)
        if critic_provider and run["status"] == "ok":
            run_critic(ctx.store, critic_provider, run["run_id"], case,
                       run["suggestion_json"])
        runs.append(run)
    return runs


def rescore_runs(ctx: AppContext, project_name: str) -> int:
    """Recompute structural checks + deterministic suggested scores for all
    successful runs (e.g. after the scoring rules changed). Human reviews are
    never touched."""
    from .checks import run_structural_checks
    from .models.suggestion import RefactoringSuggestion

    n = 0
    for run in ctx.store.list_runs(project_id=project_name, status="ok"):
        case = ctx.store.get_case(run["case_id"])
        if not case or not run.get("suggestion_json"):
            continue
        suggestion = RefactoringSuggestion.model_validate(
            json.loads(run["suggestion_json"]))
        structural = run_structural_checks(suggestion, case, run, ctx.store)
        ctx.store.update_run_checks(run["run_id"], json.dumps(structural, default=str))
        ctx.store.save_suggested_scores(run["run_id"], "deterministic",
                                        structural["suggested_scores"])
        n += 1
    ctx.store.audit("agent_run", project_name, "rescored",
                    details={"runs": n, "reason": "scoring rules updated"})
    return n


# ---------------- reviews ----------------

def save_review(ctx: AppContext, run_id: str, scores: dict[str, int],
                would_try_it: str, decision: str, reviewer_notes: str = "",
                edited_output_json: str | None = None,
                reviewer_id: str | None = None) -> HumanReview:
    run = ctx.store.get_run(run_id)
    if not run:
        raise ValueError(f"unknown run {run_id}")
    hgrs = compute_hgrs(scores, ctx.cfg.hgrs_weights)
    review = HumanReview(
        review_id=str(uuid.uuid4()), run_id=run_id,
        reviewer_id=reviewer_id or ctx.cfg.reviewer_id,
        hgrs=hgrs, would_try_it=WouldTry(would_try_it), decision=Decision(decision),
        reviewer_notes=reviewer_notes, edited_output_json=edited_output_json,
        review_timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **{c: int(scores[c]) for c in CRITERIA})
    ctx.store.save_review(review)
    return review


# ---------------- skill optimization / validation ----------------

def optimize(ctx: AppContext, skill_name: str, skill_version: str,
             provider_name: str | None = None, model_id: str | None = None) -> dict:
    digest = build_digest(ctx.store, skill_name, skill_version)
    provider = ctx.provider(provider_name, model_id)
    result = optimize_skill(ctx.cfg, ctx.store, provider, skill_name,
                            skill_version, digest)
    result["digest"] = digest
    return result


def validate(ctx: AppContext, project_name: str, skill_name: str,
             baseline_version: str, candidate_version: str,
             provider_name: str | None = None, model_id: str | None = None) -> dict:
    provider = ctx.provider(provider_name, model_id)
    return validate_skills(ctx.cfg, ctx.store, provider, project_name,
                           skill_name, baseline_version, candidate_version)


def approve_and_promote(ctx: AppContext, report_id: str,
                        approver: str | None = None) -> dict:
    return promote_candidate(ctx.cfg, ctx.store, report_id,
                             approver or ctx.cfg.reviewer_id)


# ---------------- experiments / comparison ----------------

def run_experiment(ctx: AppContext, name: str, project_name: str,
                   modes: list[str], models: list[dict],
                   skill_versions: list[str | None] | None = None,
                   split: str | None = None) -> dict:
    """Fair comparison: same cases, same evidence, varying mode/model/skill."""
    config = {"project": project_name, "modes": modes, "models": models,
              "skill_versions": skill_versions, "split": split}
    experiment_id = ctx.store.create_experiment(name, config)
    total = 0
    for model_spec in models:
        for mode in modes:
            versions = skill_versions or [None]
            if mode == "baseline":
                versions = [None]
            for sv in versions:
                runs = run_agents(
                    ctx, project_name, mode, split=split,
                    provider_name=model_spec.get("provider"),
                    model_id=model_spec.get("model_id"),
                    skill_version=sv, experiment_id=experiment_id)
                total += len(runs)
    return {"experiment_id": experiment_id, "runs": total}


def comparison_table(ctx: AppContext, project_name: str | None = None,
                     experiment_id: str | None = None) -> list[dict]:
    runs = ctx.store.list_runs(project_id=project_name, experiment_id=experiment_id)
    groups: dict[tuple, dict] = {}
    for run in runs:
        key = (run["agent_mode"], run["model_id"], run["skill_version"] or "none")
        g = groups.setdefault(key, {
            "agent_mode": key[0], "model_id": key[1], "skill_version": key[2],
            "runs": 0, "ok": 0, "invalid_json": 0, "errors": 0,
            "grounding_failures": 0, "tokens": [], "runtimes": [],
            "hgrs": [], "criteria": {c: [] for c in CRITERIA}, "would_try_yes": 0,
            "reviews": 0})
        g["runs"] += 1
        if run["status"] == "ok":
            g["ok"] += 1
        elif run["status"] == "invalid_json":
            g["invalid_json"] += 1
        else:
            g["errors"] += 1
        checks = json.loads(run.get("structural_checks_json") or "{}")
        if checks.get("critical_hallucination"):
            g["grounding_failures"] += 1
        if run.get("total_tokens"):
            g["tokens"].append(run["total_tokens"])
        if run.get("runtime_seconds"):
            g["runtimes"].append(run["runtime_seconds"])
        review = ctx.store.review_for_run(run["run_id"])
        if review:
            g["reviews"] += 1
            g["hgrs"].append(review["hgrs"])
            for c in CRITERIA:
                g["criteria"][c].append(review[c])
            if review["would_try_it"] == "yes":
                g["would_try_yes"] += 1

    def mean(xs):
        return round(sum(xs) / len(xs), 3) if xs else None

    table = []
    for g in groups.values():
        row = {
            "agent_mode": g["agent_mode"], "model_id": g["model_id"],
            "skill_version": g["skill_version"], "runs": g["runs"],
            "json_validity_rate": round(g["ok"] / g["runs"], 3) if g["runs"] else None,
            "grounding_failure_rate": round(g["grounding_failures"] / g["runs"], 3)
                if g["runs"] else None,
            "mean_hgrs": mean(g["hgrs"]),
            "reviews": g["reviews"],
            "would_try_yes_pct": round(100 * g["would_try_yes"] / g["reviews"], 1)
                if g["reviews"] else None,
            "mean_tokens": mean(g["tokens"]),
            "mean_runtime_s": mean(g["runtimes"]),
            "cost_proxy": round((mean(g["tokens"]) or 0) *
                                (mean(g["runtimes"]) or 0), 1) or None,
        }
        for c in CRITERIA:
            row[f"mean_{c}"] = mean(g["criteria"][c])
        table.append(row)
    return sorted(table, key=lambda r: (r["agent_mode"], str(r["model_id"])))


# ---------------- exports ----------------

def export_dataset(ctx: AppContext, min_hgrs: float = 4.0,
                   project: str | None = None,
                   formats: list[str] | None = None,
                   lora_prep: bool = False) -> dict:
    result = exports_mod.export_dataset(ctx.cfg, ctx.store, min_hgrs, project, formats)
    if lora_prep:
        result["lora_prep_dir"] = exports_mod.prepare_lora_workspace(
            ctx.cfg, result["out_dir"])
    return result
