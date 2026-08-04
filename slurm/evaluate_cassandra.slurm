#!/bin/bash
# DSARP — FINAL UNSEEN evaluation on apache/cassandra. Leakage-guarded.
#SBATCH --job-name=dsarp-cassandra
#SBATCH --output=logs/cassandra_%j.out
#SBATCH --time=${DSARP_TIME:-08:00:00}
#SBATCH --partition=${DSARP_GPU_PARTITION:-gpu}
#SBATCH --account=${DSARP_ACCOUNT:-CHANGE_ME}
#SBATCH --gres=gpu:${DSARP_GPUS:-1}
#SBATCH --cpus-per-task=${DSARP_CPUS:-16}
#SBATCH --mem=${DSARP_MEM:-64G}
set -euo pipefail

module load python/3.11 java/17 cuda/12.1 || true
source .venv/bin/activate || true

PORT="${DSARP_PORT:-8000}"

# 1) serve model in the background (vLLM)
python -m vllm.entrypoints.openai.api_server \
  --model "${DSARP_MODEL:-Qwen2.5-Coder-32B-Instruct}" --port "$PORT" &
SERVE_PID=$!
sleep 60

# 2) prepare + evaluate (guard blocks if cassandra leaked into training)
python scripts/run_tools.py --profile hpc --config unseen --tools arcan,designite --mode execute || true
dsarp-hpc --profile hpc source index --repo apache-cassandra || true
dsarp-hpc --profile hpc normalize --repo apache-cassandra
dsarp-hpc --profile hpc evaluate cassandra --with-normalize --top-k 3

kill $SERVE_PID || true
