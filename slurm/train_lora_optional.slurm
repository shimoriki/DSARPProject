#!/bin/bash
# DSARP — OPTIONAL LoRA fine-tune of the explanation model. Not required for the MVP.
# Guarded: refuses on too-few examples or Cassandra leakage; masked names only.
#SBATCH --job-name=dsarp-lora
#SBATCH --output=logs/lora_%j.out
#SBATCH --time=${DSARP_TIME:-24:00:00}
#SBATCH --partition=${DSARP_GPU_PARTITION:-gpu}
#SBATCH --account=${DSARP_ACCOUNT:-CHANGE_ME}
#SBATCH --gres=gpu:${DSARP_GPUS:-2}
#SBATCH --cpus-per-task=${DSARP_CPUS:-16}
#SBATCH --mem=${DSARP_MEM:-128G}
set -euo pipefail

module load python/3.11 cuda/12.1 || true
source .venv/bin/activate || true

# Dry-run first (always safe). Remove --dry-run to train when deps + data are present.
dsarp-hpc --profile hpc train lora --dataset data/training/multi_repo_train_chat.jsonl --dry-run
# dsarp-hpc --profile hpc train lora --dataset data/training/multi_repo_train_chat.jsonl
