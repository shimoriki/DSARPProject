#!/bin/bash
#SBATCH --job-name=dsarp-mine
#SBATCH --output=logs/mine_%j.out
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
set -euo pipefail

module load python/3.11 java/17 || true
source .venv/bin/activate || true

# Loops 1-3: clone + commit mining + RefactoringMiner (execute mode on HPC).
dsarp-hpc --profile hpc setup
dsarp-hpc --profile hpc repo clone --config configs/repos_train.yaml || true
# Per-repo RefactoringMiner runs are fanned out by the batch harness.
srun python scripts/mine_refactorings.py --config configs/repos_train.yaml
