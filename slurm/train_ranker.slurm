#!/bin/bash
# DSARP — build multi-repo dataset + train the preference ranker (repo-independent).
#SBATCH --job-name=dsarp-ranker
#SBATCH --output=logs/ranker_%j.out
#SBATCH --time=${DSARP_TIME:-04:00:00}
#SBATCH --partition=${DSARP_PARTITION:-compute}
#SBATCH --account=${DSARP_ACCOUNT:-CHANGE_ME}
#SBATCH --cpus-per-task=${DSARP_CPUS:-16}
#SBATCH --mem=${DSARP_MEM:-64G}
set -euo pipefail

module load python/3.11 || true
source .venv/bin/activate || true

dsarp-hpc --profile hpc setup
python scripts/align_refactorings.py --profile hpc --config train
dsarp-hpc --profile hpc dataset build-multi-repo --splits train
dsarp-hpc --profile hpc ranker train --dataset data/training/multi_repo_train_candidates.jsonl
dsarp-hpc --profile hpc validate leave-one-repo-out
dsarp-hpc --profile hpc generalisation report
