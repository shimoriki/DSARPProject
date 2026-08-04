#!/bin/bash
#SBATCH --job-name=dsarp-cassandra
#SBATCH --output=logs/cassandra_%j.out
#SBATCH --time=08:00:00
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
set -euo pipefail

module load python/3.11 java/17 cuda/12.1 || true
source .venv/bin/activate || true

# FINAL UNSEEN TEST. apache/cassandra must not appear in any training config.
# 1) serve model (vLLM) in the background
python scripts/serve_vllm.py --model Qwen2.5-Coder-32B-Instruct --port 8000 &
SERVE_PID=$!
sleep 60

# 2) full inference path 9-13 for cassandra
dsarp-hpc --profile hpc evaluate --repo apache-cassandra --with-normalize
kill $SERVE_PID || true
