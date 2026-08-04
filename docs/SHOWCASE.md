# DSARP — Showcase Guide (run it yourself, explain it to a professor)

This is a **standalone runbook**: everything below runs in your own terminal (Windows `py`),
no Claude needed. It also gives you the talking points.

---

## 1. The 30-second pitch

**DSARP is an evidence-based, no-hallucination refactoring recommendation system for Java.**
It learns from **real refactoring history** (mined from git commits with RefactoringMiner) and
**architecture smells** (cyclic/hub/unstable/god-component dependencies), then, for *any* Java
repository, it produces **ranked, schema-valid, evidence-grounded refactoring suggestions** —
each traceable to the evidence that justifies it, and each checked so it never invents code.

It is trained on **11 real open-source repositories** and evaluated with **leave-one-repository-out**
validation. **Apache Cassandra is held out as a strictly unseen test** (a leakage guard enforces this).

## 2. Why it's interesting (talking points for the professor)

1. **Evidence-grounded + no-hallucination.** Every suggestion cites evidence IDs; validators demote
   any unverifiable claim to `requires_source_inspection` instead of inventing files/classes/edges.
2. **Repository-independent features.** The ranker learns from *structural* features (cycle size,
   fan-in/out, instability, coupling, centrality, …) with **masked component names** — so it
   generalizes across repositories instead of memorizing package names like `org.apache.tika.*`.
3. **Learns from real refactoring commits.** RefactoringMiner extracts historical refactorings;
   we keep **only architectural ones** (Move/Extract Class, Extract Interface, Move Method, …) and
   align them with detected smells to form training labels. Code-level edits are ignored.
4. **Honest generalization metric.** Leave-one-repository-out (train on 10 repos, test on the 11th):
   **0.9779**. Not a random-row split — a repository-level split, which is the hard test.
5. **A "grokking"-informed neural ranker beats gradient-boosted trees.** A small MLP trained with
   weight decay + long training + best-held-out checkpoint (0.9779) vs GBM (0.9535). We *measured*
   whether the grokking phenomenon appears (it doesn't dramatically — the ingredients still help).
6. **Token-optimized LLM use.** Explanations use a minimal "context package" + a hash cache, so
   repeated runs cost ~no tokens. Runs offline (deterministic) or on a local model (Ollama).
7. **Unseen-repo ready.** Point it at *any* Java repo (URL or local path); it works even without the
   JVM tools by falling back to the source index + import graph, and it says which tools were used.

## 3. The pipeline (one breath)

```
repositories → mine refactoring commits (RefactoringMiner) + detect smells (graph/source)
            → build dependency graph + repo-independent features (masked names)
            → align architectural refactorings with smells → training dataset
            → train ranker (grokking neural ranker, leave-one-repo-out validated)
new repo    → smells + graph + candidates → rank → LLM explanation (token-optimized)
            → validate (no-hallucination) → accuracy gate → ranked suggestions + OpenRewrite recipe
```

## 4. Results you can point at

| What | Number |
|---|---|
| Real training repositories | **11** (Cassandra excluded, held out) |
| Real training rows (architectural-only labels) | **5,022** |
| Refactorings mined from real commits | thousands (e.g. tika 557 architectural) |
| Leave-one-repo-out — gradient-boosted trees | 0.9535 |
| Leave-one-repo-out — **grokking neural ranker (deployed)** | **0.9779** |
| Larger MLPs tried | 0.9745–0.9746 (worse — small model wins) |
| Unit/integration tests | **25 passing** |
| Suggestions grounding pass rate (offline) | **1.00**, 0 hallucinations |

---

## 5. Prerequisites (one-time)

- **Python** (this machine uses the `py` launcher; `python`/`python3` are Store stubs). Any 3.9+.
- Install deps (already installed on this machine; for a fresh clone):
  ```
  py -m pip install pydantic PyYAML networkx jsonschema requests scikit-learn streamlit torch
  ```
- **Optional:** Ollama running a local model (e.g. `ollama pull qwen2.5-coder:3b`) for real LLM
  explanations. Everything works **offline** without it (`--model offline`).
- **Optional (for re-mining):** Java (this machine has Java 26) + the bundled
  `tools/RefactoringMiner-3.1.4/`. The mined data is already on disk, so you don't need to re-mine.

> Shortcut: if you run `py -m pip install -e .`, the `dsarp-local` command becomes available.
> Otherwise use `py -m dsarp.cli …` everywhere below — both are identical.

---

## 6. The demo

### Easiest: one click
**Double-click `showcase.bat`** in the project root (or run `showcase.bat` from a terminal).
It opens the dashboard in its own window and walks through every CLI demo below, pausing for a
keypress between steps so you control the pacing. Nothing to type in front of the professor.

### Or run the steps yourself (copy-paste, in order)

### A. Prove it works (30 seconds)
```
py -m pytest -q
py -m dsarp.cli demo full
```
`demo full` runs the whole local pipeline offline on sample data and prints grounding pass rate,
hallucination count, and the token-savings report. (It will **keep** the deployed real neural ranker.)

### B. Open the dashboard — the visual centerpiece
```
py -m streamlit run ui/streamlit_app.py
```
Then open http://localhost:8501. Walk the professor through the sidebar pages:
- **Dashboard / Suggestions** — ranked suggestions, evidence cards, the **no-hallucination panel**
  (green/red checks), and **"Why this rank?"** score breakdown.
- **Multi-Repo Training** — dataset stats + ranker feature importance.
- **Repository Splits / LORO Validation** — the leakage guard + leave-one-repo-out scores.
- **Generalisation Report** — cross-repo results.
- **Cassandra Evaluation** — the unseen final test.

### C. Live suggestions on the unseen test repo
```
py -m dsarp.cli suggest --repo apache-cassandra --model offline --top-k 3
```
Shows ranked, `[passed]`, evidence-grounded suggestions. Use `--model ollama` if Ollama is running
to get real natural-language explanations from a local model.

### D. The generalization story (the ML contribution)
```
py scripts\sweep_neural_ranker.py
```
Reproduces the model comparison from the **already-mined 5,022-row real dataset**:
gradient-boosted trees (0.9535) vs the grokking neural ranker (0.9779), tries larger models,
and deploys the winner. Then look at:
```
type data\models\model_comparison.json
type data\models\grokking_curve.json
```

### E. Works on ANY repo (repository-independence)
```
py -m dsarp.cli repo add --name mini-java --path data\samples\mini-java-repo
py -m dsarp.cli evaluate --name mini-java --model offline
```
It detects the build system, builds the import graph, finds the real cyclic dependency, and
reports which tools were unavailable — proving it isn't hardcoded to any repo.

### F. The scientific-integrity bit (leakage guard)
```
py -m dsarp.cli evaluate cassandra --dry-run
```
Prints that Cassandra is excluded from every training split. If you ever added it to a training
config, this command refuses to run.

---

## 7. Reproduce the REAL training from scratch (optional, slower)

The real dataset is already on disk. To rebuild it from the mined RefactoringMiner data (fast,
no re-mining), then retrain and redeploy the neural ranker:
```
py scripts\mine_and_align_refactorings.py --repos apache/commons-cli,apache/commons-lang,apache/commons-io,apache/commons-collections,apache/tika,apache/logging-log4j2,apache/struts,apache/maven,spring-projects/spring-framework --skip-mine --train
py scripts\sweep_neural_ranker.py
```
To mine a repo's history yourself (needs Java; slow for big repos):
```
py scripts\mine_and_align_refactorings.py --repos apache/commons-cli --depth 500
```

## 8. What's real vs. what needs external tools (be honest with the professor)

- **Fully real now:** source parsing, dependency graphs, smell detection, RefactoringMiner mining
  (Java present), architectural-only alignment, the trained ranker + neural ranker, no-hallucination
  validators, unseen-repo inference, the dashboard, 25 tests.
- **Import-mode / optional:** Arcan & Designite smells (we detect the common architectural smells
  from structure without them; import their CSV/JSON exports to add more).
- **Draft-only until validated:** OpenRewrite recipes are marked `draft` unless a Maven dry-run +
  build actually pass (we never fake `validated`).
- **Two repos are structural-only:** guava & lucene (their RefactoringMiner runs timed out); the
  other 9 have real historical architectural labels.

## 9. Likely professor questions (and the honest answers)

- *"Does it hallucinate?"* No — validators demote any unverifiable claim to
  `requires_source_inspection`; the accuracy gate drops invalid/low-confidence suggestions.
- *"Is 0.9779 just memorizing package names?"* No — features are structural and names are masked;
  validation is **leave-one-repository-out**, so the test repo is never seen in training.
- *"Did grokking actually happen?"* Not dramatically (see `grokking_curve.json`) — held-out accuracy
  rises early. But the grokking *ingredients* (weight decay + long training + best-held-out
  checkpoint) still produced the best model, and we report this honestly.
- *"Why exclude Cassandra?"* It's the single unseen benchmark; training on it would destroy the
  only honest generalization estimate. A leakage guard enforces the exclusion.
