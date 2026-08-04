#!/bin/bash
# DSARP — serve a coder model with vLLM (OpenAI-compatible). No cloud dependency.
#SBATCH --job-name=dsarp-vllm
#SBATCH --output=logs/vllm_%j.out
#SBATCH --time=${DSARP_TIME:-08:00:00}
#SBATCH --partition=${DSARP_GPU_PARTITION:-gpu}
#SBATCH --account=${DSARP_ACCOUNT:-CHANGE_ME}
#SBATCH --gres=gpu:${DSARP_GPUS:-1}
#SBATCH --cpus-per-task=${DSARP_CPUS:-16}
#SBATCH --mem=${DSARP_MEM:-64G}
set -euo pipefail

# --- parameters (override via env) ------------------------------------------
MODEL="${DSARP_MODEL:-Qwen2.5-Coder-32B-Instruct}"
PORT="${DSARP_PORT:-8000}"
TP_SIZE="${DSARP_TP_SIZE:-${DSARP_GPUS:-1}}"

module load python/3.11 cuda/12.1 || true
source .venv/bin/activate || true

echo "[vllm] serving $MODEL on :$PORT (tensor-parallel=$TP_SIZE)"
srun python -m vllm.entrypoints.openai.api_server \
  --model "$MODEL" --port "$PORT" --tensor-parallel-size "$TP_SIZE"
