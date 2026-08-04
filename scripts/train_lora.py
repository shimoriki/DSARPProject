"""Loop 8 (optional, HPC) — LoRA fine-tune of the explanation model.

MVP does NOT require this. This is a guarded entrypoint: it validates the dataset
and prints the trainer plan. Wire PEFT/transformers here on the cluster. It never
runs on the laptop profile and never uses cloud APIs.
"""
import argparse
from pathlib import Path

import _bootstrap  # noqa: F401
from dsarp.util import read_jsonl


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-model", default="Qwen2.5-Coder-7B-Instruct")
    ap.add_argument("--dataset", default="data/training/chat.jsonl")
    ap.add_argument("--output", default="data/training/lora_adapter")
    args = ap.parse_args()
    ds = Path(args.dataset)
    n = sum(1 for _ in read_jsonl(ds)) if ds.exists() else 0
    print(f"[lora] base={args.base_model} dataset={ds} records={n} -> {args.output}")
    if n == 0:
        print("[lora] no chat records; build the dataset first (build_training_dataset.py).")
        return 1
    print("[lora] plan: PEFT LoRA (r=16, alpha=32) over masked chat records; "
          "run inside train_lora.slurm on GPU nodes. Trainer wiring is a TODO stub "
          "(transformers+peft) — intentionally not executed here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
