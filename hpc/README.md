# Agentic RefAgent arm on HPC

This folder runs the agentic arm of DSARP (`dsarp/agentic/`) on a GPU node. The arm follows RefAgent (Oueslati, Lamothe, Khomh, arXiv 2511.03153), adapted to architectural refactoring. An LLM plans how to break one package cycle. Deterministic engines apply the plan. A compiler and tester repair loop fixes what breaks. The same gates as the beam arm decide acceptance: Maven build, the project's full test suite, ArchUnit, reflection and services. Arcan and japicmp counts are reported alongside.

On the laptop, all seven local Ollama models (7B and smaller, on CPU) failed the model check. This job runs the open models from the paper, plus one newer coder model, at full precision on an A100.

## What has to be on the cluster

| Path | Source | Why |
|---|---|---|
| The whole DSARP checkout, branch `cycle-repair-loop` | `git clone` | `dsarp/` package, `tools/dsarp-spoon`, `tools/dsarp-archunit`, `pyproject.toml` |
| `hpc/README.md` | git | This file |
| `hpc/setup.sh` | git | Creates `.venv` (DSARP + vLLM) and clones the four Java repos at pinned commits |
| `hpc/run_refagent.slurm` | git | The job: serve the model, run the model check, then freeze, confirm and repair on Tika |
| `hpc/smoke.py` | git | Model check on Commons Exec, Math and Text; bar is 2 of 3 |
| `hpc/tika/targets.json` | git | The five Tika 697d7c0 package cycles the beam arm and the teammate pipeline were measured on |
| `tools/arcan-1.2.1/` (jar + `lib/`, 144 MB) | **copy by hand**, not in git | Arcan smell detection. It is a symlink in the worktree; copy the real folder |

Maven, japicmp and the Spoon and ArchUnit drivers need no copying. Maven comes from `module load maven` or `tools/apache-maven-*`. The code fetches japicmp from Maven Central on first use, and builds the drivers from `tools/` with Maven.

The cluster needs Python 3.11, CUDA 12.x, JDK 17 as the default `java`, Maven 3.9, and network access to Maven Central, GitHub and Hugging Face. If a model download asks for a login, set `HF_TOKEN`.

## Models

| `MODEL` (Hugging Face id) | In the paper | Size, bf16 | Fits one A100 80 GB |
|---|---|---|---|
| `deepseek-ai/deepseek-coder-33b-instruct` | yes, reported on par with GPT-4o (Table 3) | about 66 GB | yes, `MAXLEN=16384` |
| `bigcode/starcoder2-15b-instruct-v0.1` | yes | about 32 GB | yes |
| `Qwen/Qwen2.5-Coder-32B-Instruct` | no (newer; our addition) | about 65 GB | yes, `MAXLEN=16384` |

The paper's main model is GPT-4o, reached through the OpenAI API. It does not need the cluster. The same scripts accept `--base-url https://api.openai.com --api-key-env OPENAI_API_KEY`. That run sends source code to OpenAI, which is acceptable for public Apache code only.

## Run

From the root of the DSARP checkout:

```bash
bash hpc/setup.sh
sbatch --account=<acct> --export=ALL,MODEL=deepseek-ai/deepseek-coder-33b-instruct hpc/run_refagent.slurm
sbatch --account=<acct> --export=ALL,MODEL=bigcode/starcoder2-15b-instruct-v0.1 hpc/run_refagent.slurm
sbatch --account=<acct> --export=ALL,MODEL=Qwen/Qwen2.5-Coder-32B-Instruct hpc/run_refagent.slurm
```

Change `--partition`, `--time` or `--gres` on the `sbatch` line if the cluster needs it. `#SBATCH` lines cannot read variables.

| Variable | Default | Meaning |
|---|---|---|
| `MODEL` | `deepseek-ai/deepseek-coder-33b-instruct` | Model to serve |
| `BUDGET` | `20` | Repair rounds per target, as in RefAgent's compiler and tester loops |
| `FORCE` | `0` | `1` runs Tika even when the model check fails |
| `MAXLEN` | `16384` | vLLM context length |
| `DSARP_REPOS` | `hpc/repos` | Where `setup.sh` cloned the Java repos |
| `DSARP_OUT` | `hpc/runs` | Output root; each job writes `<root>/<model>_<jobid>/` |

Each job runs these steps:

1. Start vLLM on 127.0.0.1 and wait for it to load.
2. Run `smoke.py`, the model check. If fewer than 2 of 3 cases pass, the job stops, unless `FORCE=1`.
3. Copy Tika and run its full test suite once as the baseline. The suite has 2,324 tests; budget 1 to 2 hours.
4. Freeze the LLM plans for the five targets.
5. Confirm the frozen plans through every gate without repair.
6. Run the repair arm, with up to `BUDGET` rounds, on targets that failed at build or tests.

Expect 10 to 30 hours in total. Most of it is Maven test runs, not the GPU.

## What to send back

Send the folder `hpc/runs/<model>_<jobid>/` without `baseline_tree/` and `work/`, which are large and rebuildable. Include `hpc/logs/refagent_<jobid>.out`. The files that matter:

- `smoke.log`: the `MODEL CHECK ... of 3` line.
- `tika/rows.jsonl`, `tika/summary.json`: the arm without repair.
- `tika_repair/rows_repair.jsonl`, `tika_repair/summary_repair.json`: the repair arm.
- `tika/preregistration.json`: the frozen LLM plans.
- `targets/baseline_tests.json`: the baseline the verdicts compare against.

These files are joined with the beam and teammate results in `docs/pipeline_comparison_tika.xlsx`.

## How this differs from the paper

| | RefAgent (paper) | This run |
|---|---|---|
| Unit | One class and its first-degree jdeps neighbours | One package cycle |
| Refactorings | 23 class-level types (Extract Method, Rename, and others) | Move class between packages, with deprecated facades at the old names |
| Who writes code | The LLM returns the whole class | Deterministic engine; the LLM plans and proposes scoped search/replace repairs |
| Loops | Compiler and tester, up to 20 rounds | Same cap (`BUDGET=20`); repair limited to files the plan touched |
| Tests | Developer tests plus EvoSuite | The project's full suite with flake reruns; no EvoSuite |
| Decoding | GPT-4o at temperature 0.7 | Temperature 0.2 with JSON mode, for every model |
| Acceptance | Compiles and tests pass | Build, tests, ArchUnit, reflection, services; Arcan and japicmp reported |

The paper's numbers (90% median test pass, 52.5% median smell reduction) come from class-level refactorings. They are a reference point, not a like-for-like target.

## Not verified

The scripts have been checked for syntax and argument wiring on Windows only. The first Linux job is their real test. On Linux, `select_jdk` finds no JDK by its Windows search paths, so it keeps the `JAVA_HOME` the module sets. That JDK must be 17.
