#!/bin/bash
#SBATCH --job-name=dsarp-lora
#SBATCH --output=logs/lora_%j.out
#SBATCH --time=24:00:00
#SBATCH --gres=gpu:2
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
set -euo pipefail

module load python/3.11 cuda/12.1 || true
source .venv/bin/activate || true

# Optional LoRA fine-tune of the explanation model on masked chat records.
# MVP does NOT require this. See scripts/train_lora.py for the trainer wiring.
srun python scripts/train_lora.py \
  --base-model Qwen2.5-Coder-7B-Instruct \
  --dataset data/training/chat.jsonl \
  --output data/training/lora_adapter
