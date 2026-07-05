"""Dataset export: reviewed, high-quality examples only.

Formats: JSONL instruction dataset, JSONL chat dataset, CSV review dataset,
plus an optional LoRA preparation folder (config stub + notes). Exporting
never trains anything — fine-tuning is an explicitly separate, later stage
that needs a sufficiently large reviewed dataset.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .config import AppConfig
from .hgrs import CRITERIA
from .log import get_logger
from .store.repos import Store

log = get_logger("exports")


def _collect_examples(store: Store, min_hgrs: float,
                      project: str | None = None) -> list[dict]:
    reviews = store.list_reviews(project_id=project)
    examples = []
    for rv in reviews:
        if rv["hgrs"] < min_hgrs:
            continue
        run = store.get_run(rv["run_id"])
        if not run or run["status"] != "ok":
            continue
        case = store.get_case(run["case_id"])
        if not case:
            continue
        preferred = rv.get("edited_output_json") or run["suggestion_json"]
        examples.append({
            "run_id": run["run_id"],
            "case": case.public_dict(),
            "skill_name": run.get("skill_name"),
            "skill_version": run.get("skill_version"),
            "agent_mode": run["agent_mode"],
            "model_id": run.get("model_id"),
            "agent_output": run["suggestion_json"],
            "preferred_output": preferred,
            "human_edited": bool(rv.get("edited_output_json")),
            "hgrs": rv["hgrs"],
            "criteria": {c: rv[c] for c in CRITERIA},
            "reviewer_notes": rv.get("reviewer_notes") or "",
            "decision": rv["decision"],
            "would_try_it": rv["would_try_it"],
        })
    return examples


_INSTRUCTION = ("Propose one evidence-grounded architectural refactoring for the "
                "following smell case. Answer with the required JSON object only.")


def export_dataset(cfg: AppConfig, store: Store, min_hgrs: float = 4.0,
                   project: str | None = None,
                   formats: list[str] | None = None) -> dict:
    formats = formats or ["instruction", "chat", "csv"]
    examples = _collect_examples(store, min_hgrs, project)
    if not examples:
        raise ValueError(f"no reviewed examples with HGRS >= {min_hgrs}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = cfg.data_path / "exports" / f"dataset_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}

    if "instruction" in formats:
        path = out_dir / "instruction_dataset.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for ex in examples:
                fh.write(json.dumps({
                    "instruction": _INSTRUCTION,
                    "input": json.dumps(ex["case"]),
                    "output": ex["preferred_output"],
                    "meta": {k: ex[k] for k in
                             ("run_id", "skill_version", "agent_mode", "model_id",
                              "hgrs", "decision", "would_try_it", "human_edited",
                              "criteria", "reviewer_notes")},
                }) + "\n")
        written["instruction"] = str(path)

    if "chat" in formats:
        path = out_dir / "chat_dataset.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for ex in examples:
                fh.write(json.dumps({"messages": [
                    {"role": "system", "content": _INSTRUCTION},
                    {"role": "user", "content": json.dumps(ex["case"])},
                    {"role": "assistant", "content": ex["preferred_output"]},
                ], "meta": {"hgrs": ex["hgrs"], "run_id": ex["run_id"],
                            "skill_version": ex["skill_version"],
                            "human_edited": ex["human_edited"]}}) + "\n")
        written["chat"] = str(path)

    if "csv" in formats:
        path = out_dir / "review_dataset.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["run_id", "agent_mode", "model_id", "skill_version",
                             *CRITERIA, "hgrs", "decision", "would_try_it",
                             "human_edited", "reviewer_notes"])
            for ex in examples:
                writer.writerow([ex["run_id"], ex["agent_mode"], ex["model_id"],
                                 ex["skill_version"],
                                 *[ex["criteria"][c] for c in CRITERIA],
                                 ex["hgrs"], ex["decision"], ex["would_try_it"],
                                 ex["human_edited"], ex["reviewer_notes"]])
        written["csv"] = str(path)

    store.audit("export", str(out_dir), "dataset_export",
                details={"examples": len(examples), "min_hgrs": min_hgrs,
                         "formats": formats})
    log.info("exported %d examples to %s", len(examples), out_dir)
    return {"out_dir": str(out_dir), "examples": len(examples), "files": written}


def prepare_lora_workspace(cfg: AppConfig, dataset_dir: str) -> str:
    """Write a LoRA preparation folder next to an exported dataset.

    This only stages files and documentation. It deliberately does NOT train:
    skill optimization (text-space) is the default improvement path; LoRA
    fine-tuning is a later stage that needs a large reviewed dataset.
    """
    src = Path(dataset_dir)
    work = src / "lora_prep"
    work.mkdir(parents=True, exist_ok=True)
    (work / "lora_config.example.yaml").write_text(
        "# Example PEFT/LoRA settings for a LOCAL fine-tune (e.g. with peft + trl).\n"
        "# Review dataset size first: a handful of reviews is NOT enough.\n"
        "base_model: Qwen/Qwen2.5-Coder-7B-Instruct   # or any local model path\n"
        "dataset: ../chat_dataset.jsonl\n"
        "format: chat\n"
        "lora:\n  r: 16\n  alpha: 32\n  dropout: 0.05\n"
        "  target_modules: [q_proj, k_proj, v_proj, o_proj]\n"
        "train:\n  epochs: 3\n  lr: 2.0e-4\n  batch_size: 4\n  gradient_accumulation: 4\n",
        encoding="utf-8")
    (work / "README.md").write_text(
        "# LoRA preparation (optional, later stage)\n\n"
        "Skill optimization updates prompts and reusable agent skills and is the\n"
        "default improvement loop. Fine-tuning changes model weights and should\n"
        "only be attempted with a sufficiently large, human-reviewed dataset\n"
        "(hundreds of accepted examples, not dozens).\n\n"
        "The chat_dataset.jsonl in the parent folder is already in a standard\n"
        "messages format usable by trl's SFTTrainer or axolotl. Nothing here\n"
        "runs automatically.\n",
        encoding="utf-8")
    return str(work)
