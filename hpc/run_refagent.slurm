#!/bin/bash
# Agentic RefAgent arm on one GPU node: serve one model with vLLM, run the model check, then
# freeze -> confirm -> repair on Tika 697d7c0's five beam targets. See hpc/README.md.
#
#   sbatch --account=<acct> --export=ALL,MODEL=deepseek-ai/deepseek-coder-33b-instruct hpc/run_refagent.slurm
#
# #SBATCH lines cannot read variables; override them on the sbatch command line instead.
#SBATCH --job-name=dsarp-refagent
#SBATCH --output=hpc/logs/refagent_%j.out
#SBATCH --time=48:00:00
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
set -euo pipefail

MODEL="${MODEL:-deepseek-ai/deepseek-coder-33b-instruct}"   # Hugging Face id, see README table
SERVED="${SERVED:-$(basename "$MODEL")}"
MAXLEN="${MAXLEN:-16384}"
PORT="${PORT:-8000}"
BUDGET="${BUDGET:-20}"             # repair rounds; RefAgent's compiler and tester loops cap at 20
FORCE="${FORCE:-0}"                # 1 = run Tika even when the model check fails
REPOS="${DSARP_REPOS:-$PWD/hpc/repos}"
OUT="${DSARP_OUT:-$PWD/hpc/runs}/${SERVED}_${SLURM_JOB_ID:-local}"
URL="http://127.0.0.1:$PORT"

module load python/3.11 cuda/12.1 java/17 maven 2>/dev/null || true
source .venv/bin/activate
export PYTHONIOENCODING=utf-8 PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$OUT" hpc/logs
echo "== $(date +%F_%T) model=$MODEL served=$SERVED out=$OUT"
java -version 2>&1 | head -1

python -m vllm.entrypoints.openai.api_server --model "$MODEL" --served-model-name "$SERVED" \
  --host 127.0.0.1 --port "$PORT" --max-model-len "$MAXLEN" --dtype bfloat16 \
  > "$OUT/vllm.log" 2>&1 &
VLLM=$!
trap 'kill $VLLM 2>/dev/null || true' EXIT
for i in $(seq 1 180); do                       # weights load: up to 30 min
  curl -sf "$URL/v1/models" >/dev/null && break
  kill -0 $VLLM 2>/dev/null || { echo "vLLM died, see $OUT/vllm.log"; tail -20 "$OUT/vllm.log"; exit 1; }
  sleep 10
done
curl -sf "$URL/v1/models" >/dev/null || { echo "vLLM not ready after 30 min"; exit 1; }
echo "== $(date +%T) vLLM ready"

# 1. Model check (bar: 2 of 3).
python hpc/smoke.py "$SERVED" "$REPOS" "$OUT/smoke" --base-url "$URL" 2>&1 | tee "$OUT/smoke.log"
PASSED=$(grep -oP 'MODEL CHECK .*: \K[0-9]+' "$OUT/smoke.log" || echo 0)
if [ "$PASSED" -lt 2 ] && [ "$FORCE" != 1 ]; then
  echo "== model check failed ($PASSED of 3); Tika skipped. FORCE=1 runs it anyway."; exit 0
fi

# 2. Baseline: a fresh copy of Tika, built and tested exactly as candidates will be.
mkdir -p "$OUT/targets"
cp hpc/tika/targets.json "$OUT/targets/targets.json"
python - "$REPOS/tika" "$OUT" <<'EOF'
import json, sys
from pathlib import Path
from dsarp.tools.arcan_runner import run_tests, select_jdk
from dsarp.verification.effect_checker import _copy_repo
src, out = Path(sys.argv[1]), Path(sys.argv[2])
tree, cache = out / "baseline_tree", out / "targets" / "baseline_tests.json"
if not tree.exists():
    _copy_repo(src, tree)
print("java level %s, JDK %s" % select_jdk(tree), flush=True)
if not cache.exists():
    t = run_tests(tree, timeout=4 * 3600, log_path=out / "baseline_tests.log")
    cache.write_text(json.dumps(t), encoding="utf-8")
t = json.loads(cache.read_text(encoding="utf-8"))
print("baseline tests:", {k: t.get(k) for k in ("tests_run", "failures", "errors", "partial", "skipped_modules")})
EOF

COMMON=(--targets-from "$OUT/targets/targets.json" --model "$SERVED"
        --base-url "$URL" --engine text --facades --rounds 3)
TREE="$OUT/baseline_tree"

# 3. Freeze the LLM plans, then confirm them through every gate without repair.
echo "== $(date +%T) freeze";  python -m dsarp.agentic.run "$TREE" "$OUT/tika" "${COMMON[@]}" --freeze
echo "== $(date +%T) confirm"; python -m dsarp.agentic.run "$TREE" "$OUT/tika" "${COMMON[@]}" --confirm --repair-budget 0

# 4. Repair arm: only targets that failed at build or tests, elsewhere the hook never fires.
python - "$OUT/tika" "$OUT/tika_repair" <<'EOF'
import json, shutil, sys
from pathlib import Path
o, r = Path(sys.argv[1]), Path(sys.argv[2])
rows = [json.loads(l) for l in (o / "rows.jsonl").read_text(encoding="utf-8").splitlines()]
bad = [x["component"] for x in rows if x.get("stage") == "build" or
       ((x.get("verdict") or {}).get("failed_gate") in ("behavioural", "tests"))]
pre = json.loads((o / "preregistration.json").read_text(encoding="utf-8"))
pre["plans"] = [p for p in pre["plans"] if p["component"] in bad]
r.mkdir(parents=True, exist_ok=True)
(r / "preregistration.json").write_text(json.dumps(pre, indent=1), encoding="utf-8")
shutil.copy(o / "baseline.json", r / "baseline.json")
if not (r / "arcan_before").exists():
    shutil.copytree(o / "arcan_before", r / "arcan_before")
print("repair targets:", len(pre["plans"]))
EOF
echo "== $(date +%T) repair budget $BUDGET"
python -m dsarp.agentic.run "$TREE" "$OUT/tika_repair" "${COMMON[@]}" --confirm --repair-budget "$BUDGET"
echo "== $(date +%T) done: send back $OUT without baseline_tree/ and work/"
