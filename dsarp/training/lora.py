"""Task 12 — guarded LoRA training workflow.

Never required for the MVP. It validates dataset size, blocks Cassandra/unseen leakage,
uses masked names (dataset already masked), writes a training config, and only runs a
real fit if PEFT/TRL + torch are installed AND enough examples exist. Otherwise it emits
a precise plan and fails gracefully.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import Config
from ..splits.manager import SplitManager
from ..util import read_jsonl, write_json

MIN_EXAMPLES = 200  # refuse real training below this


def _deps_available() -> bool:
    try:
        import peft  # noqa: F401
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except Exception:
        return False


def lora_train(cfg: Config, dataset: Optional[Path] = None, dry_run: bool = True) -> Dict[str, Any]:
    dataset = Path(dataset) if dataset else (cfg.data_dir / "training" / "multi_repo_train_chat.jsonl")
    lora_cfg = cfg.get("lora", {}) or {}
    base_model = lora_cfg.get("base_model", "Qwen2.5-Coder-7B-Instruct")
    out_dir = cfg.data_dir / "models" / "lora_adapter"

    # leakage guard on the source split configuration
    try:
        SplitManager().assert_no_leakage()
    except Exception as e:
        return {"ok": False, "status": "leakage_blocked", "message": str(e)}

    rows = list(read_jsonl(dataset)) if dataset.exists() else []
    # extra guard: drop any record whose project_id is not trainable
    sm = SplitManager()
    rows = [r for r in rows if sm.is_training_allowed(r.get("project_id", "trainable"))]
    n = len(rows)

    training_config = {
        "base_model": base_model, "dataset": str(dataset), "examples": n,
        "output": str(out_dir), "lora": {"r": 16, "alpha": 32, "dropout": 0.05},
        "masked_names": True, "excluded_repositories": sm.unseen,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(cfg.data_dir / "models" / "lora_training_config.json", training_config)

    if n < MIN_EXAMPLES:
        return {"ok": False, "status": "too_few_examples",
                "message": f"{n} examples < min {MIN_EXAMPLES}; build a larger multi-repo dataset. "
                           f"Wrote plan to models/lora_training_config.json"}
    if dry_run or not _deps_available():
        reason = "dry-run" if dry_run else "peft/torch/transformers not installed"
        return {"ok": True, "status": "planned",
                "message": f"{reason}. Config written; run on GPU node via slurm/train_lora_optional.slurm"}
    # Real training path (only reached with deps + enough data + not dry-run).
    try:  # pragma: no cover - requires GPU stack
        from .lora_impl import run_peft_lora
        model_path = run_peft_lora(training_config, rows, out_dir)
        return {"ok": True, "status": "trained", "message": f"adapter -> {model_path}"}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "status": "failed", "message": str(exc)[:300]}
