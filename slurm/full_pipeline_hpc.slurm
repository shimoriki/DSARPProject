#!/bin/bash
# DSARP — full HPC pipeline as a dependency chain (mine -> dataset/ranker -> serve -> evaluate).
# Submits child jobs with afterok dependencies. Parameterize via env vars (see other scripts).
#SBATCH --job-name=dsarp-full
#SBATCH --output=logs/full_%j.out
#SBATCH --time=00:10:00
#SBATCH --partition=${DSARP_PARTITION:-compute}
#SBATCH --account=${DSARP_ACCOUNT:-CHANGE_ME}
set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-.}"
J1=$(sbatch --parsable slurm/mine_all_repos.slurm)
J2=$(sbatch --parsable --dependency=afterok:$J1 slurm/train_ranker.slurm)
J3=$(sbatch --parsable --dependency=afterok:$J2 slurm/evaluate_cassandra.slurm)
echo "[full] submitted mine=$J1 -> ranker=$J2 -> cassandra=$J3"
echo "[full] LoRA is optional: sbatch slurm/train_lora_optional.slurm"
