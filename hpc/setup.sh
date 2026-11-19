#!/bin/bash
# One-time setup on the HPC login node, from the root of the DSARP checkout:  bash hpc/setup.sh
# Creates .venv with DSARP + vLLM, and clones the four Java repositories at the pinned commits.
# Needs network for pip, git and Maven Central. Arcan is NOT downloadable: copy it (see README).
set -euo pipefail

REPOS="${DSARP_REPOS:-$PWD/hpc/repos}"

module load python/3.11 cuda/12.1 2>/dev/null || true
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e . vllm

mkdir -p "$REPOS" hpc/logs           # sbatch writes hpc/logs/refagent_<job>.out and won't create it
clone() {  # name url sha
  [ -d "$REPOS/$1" ] || git clone --quiet "$2" "$REPOS/$1"
  git -c advice.detachedHead=false -C "$REPOS/$1" checkout --quiet "$3"
  echo "$1 at $(git -C "$REPOS/$1" rev-parse --short HEAD)"
}
clone tika                https://github.com/apache/tika.git         697d7c0
clone apache-commons-exec https://github.com/apache/commons-exec.git 4a27212367272c91da8dc01732f9c20be964de48
clone apache-commons-math https://github.com/apache/commons-math.git e253f396ba47edf008f60c903c4623496c7eef49
clone apache-commons-text https://github.com/apache/commons-text.git 79083a00a3c593592a42dd975b6e9ed27e35179a

# The gates need these on every node: fail now rather than six hours into a job.
command -v mvn >/dev/null || ls tools/apache-maven-*/bin/mvn >/dev/null 2>&1 || echo "MISSING: mvn (module load maven, or unpack Maven 3.9.x into tools/)"
ls tools/arcan-*/arcan-*.jar >/dev/null 2>&1 && ls tools/arcan-*/lib/*.jar >/dev/null 2>&1 || echo "MISSING: tools/arcan-1.2.1/ (full distribution: jar + lib/)"
java -version 2>&1 | grep -q '"17' || echo "MISSING: JDK 17 as default java (module load java/17, set JAVA_HOME)"
echo "setup done; repos in $REPOS"
