#!/bin/bash
#SBATCH --job-name=dsarp-dataset
#SBATCH --output=logs/dataset_%j.out
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
set -euo pipefail

module load python/3.11 java/17 || true
source .venv/bin/activate || true

# Loops 4-7: tool evidence + graphs + alignment + dataset (large).
srun python scripts/run_tools.py --config configs/repos_train.yaml --tools arcan,designite,graph
srun python scripts/build_graphs.py --config configs/repos_train.yaml
srun python scripts/align_refactorings.py --config configs/repos_train.yaml
srun python scripts/build_training_dataset.py --large
dsarp-hpc --profile hpc ranker train --dataset data/training/candidates.jsonl
