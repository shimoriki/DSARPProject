#!/bin/bash
# DSARP — clone + mine RefactoringMiner + import/execute tools for ALL training repos.
#SBATCH --job-name=dsarp-mine-all
#SBATCH --output=logs/mine_all_%j.out
#SBATCH --time=${DSARP_TIME:-12:00:00}
#SBATCH --partition=${DSARP_PARTITION:-compute}
#SBATCH --account=${DSARP_ACCOUNT:-CHANGE_ME}
#SBATCH --cpus-per-task=${DSARP_CPUS:-16}
#SBATCH --mem=${DSARP_MEM:-64G}
set -euo pipefail

module load python/3.11 java/17 || true
source .venv/bin/activate || true

CONFIG="${DSARP_TRAIN_CONFIG:-train}"   # repos_train.yaml

dsarp-hpc --profile hpc setup
python scripts/clone_repos.py --profile hpc --config "$CONFIG"
python scripts/mine_refactorings.py --profile hpc --config "$CONFIG"
python scripts/run_tools.py --profile hpc --config "$CONFIG" --tools arcan,designite --mode execute
python scripts/build_graphs.py --profile hpc --config "$CONFIG"
# NOTE: Cassandra is NOT in repos_train.yaml — it is never mined for training.
