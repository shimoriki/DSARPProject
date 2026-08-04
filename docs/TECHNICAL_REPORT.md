# DSARP: An Evidence-Based, No-Hallucination Refactoring Recommendation System

**Technical Report / Methodology**
*DSARP — Data-driven Software Architecture Refactoring Pipeline*

---

## Abstract

We present DSARP, a modular system that recommends architectural refactorings for Java
repositories. Unlike prompt-only LLM assistants, DSARP grounds every recommendation in
*verifiable evidence* mined from three sources: (i) real refactoring operations extracted
from version-control history with **RefactoringMiner**, (ii) architectural **smells** detected
from the dependency graph and source index (with optional **Arcan**/**Designite** import),
and (iii) structural graph metrics. Recommendations are produced by a deterministic candidate
generator plus a learned **preference ranker** trained on **repository-independent structural
features**, validated with **leave-one-repository-out (LORO)** cross-validation, and filtered by
a suite of **no-hallucination validators**. We deploy a *grokking-informed* neural ranker that
attains **0.978 LORO accuracy**, improving on gradient-boosted trees (0.954). Apache Cassandra is
held out as a strictly unseen test repository, enforced by a leakage guard. This report documents
the approaches we considered, the methodology in academic detail, the tooling and its exact usage,
current results, threats to validity, and a concrete improvement roadmap.

---

## 1. Introduction and problem statement

Large codebases accumulate *architectural technical debt*: cyclic dependencies between packages,
"god" components, hub-like and unstable dependencies. Refactoring can repay this debt, but deciding
*which* refactoring to apply *where* is expensive and error-prone. Two failure modes dominate
existing automation:

1. **Hallucination.** LLM assistants invent classes, methods, or dependency edges that do not exist,
   producing plausible-but-wrong suggestions.
2. **Non-generalization.** Models trained on one project memorize project-specific names and fail
   to transfer to unseen repositories.

DSARP addresses both. It (a) requires every claim to trace to an evidence identifier, demoting
unverifiable claims to `requires_source_inspection` rather than fabricating, and (b) trains only on
*structural, name-masked* features so the ranker generalizes across repositories. The design goal is
a system whose suggestions are **ranked best-to-worst, schema-valid, evidence-grounded, and safe**,
and whose outputs are consumable by other agents through a stable schema.

---

## 2. Approaches considered (design evolution)

The current system is the outcome of several iterations. We document each, including those we
rejected, because the rejections are themselves findings.

### 2.1 Evidence source: synthetic → weak → real labels

| Stage | Label source | Rationale | Outcome |
|---|---|---|---|
| **A. Synthetic fixtures** | Hand-generated smells/graphs with distinct namespaces | Bootstrap the pipeline with zero external tooling; verify repo-independence | Proved the pipeline and masking, but LORO was *degenerate* (≈1.0) because labels were a deterministic function of features |
| **B. Real repos, weak supervision** | Real dependency-graph smells + graph-derived weak labels (a candidate that breaks a real cycle is positive) | Train on real structure without a JVM miner | Genuine structural signal; but labels still largely graph-deterministic (LORO ≈0.95–0.97) |
| **C. Real historical labels (current)** | **RefactoringMiner** architectural refactorings aligned to smells | Learn from what developers *actually did* | Non-degenerate LORO (0.95–0.98); `graph_delta` no longer dominates feature importance |

Stage C is the scientifically strongest because the positive class is anchored in observed developer
behavior, not a rule we wrote.

### 2.2 Ranker family: deterministic → trees → neural (grokking)

- **Deterministic weighted score.** A hand-weighted linear combination of features. Always available,
  no training. Used as the zero-data baseline and as a fusion term.
- **Gradient-boosted trees** (scikit-learn `GradientBoostingClassifier`, optionally LightGBM). Strong
  tabular baseline; **LORO = 0.9535**.
- **Grokking-informed neural ranker (deployed).** A small multilayer perceptron trained with weight
  decay and long training, motivated by the *grokking* phenomenon (Power et al., 2022). **LORO =
  0.9779.** We explicitly tested whether grokking (delayed generalization) manifests; it does *not*
  dramatically (§6.9), but its training ingredients still yielded the best model.
- **Rejected: larger networks.** MLPs of size (128,64) and (128,64,32) scored 0.9745–0.9746 — *worse*
  than the (64,32) model. Capacity is not the bottleneck.
- **Considered, optional: LoRA fine-tuning** of the explanation LLM. Guarded and dry-runnable, but not
  required for the MVP; deferred until the masked instruction dataset is large enough.

### 2.3 History depth and scale

- **Shallow (depth-1) clones** are fast but carry *no history*, so RefactoringMiner cannot run.
- **Deepening** a depth-1 clone (`git fetch --depth N`) proved to be the dominant cost for large repos
  (one repository's deepen+mine took ~83 min).
- **Fresh shallow clone** (`git clone --depth N`) is more efficient than deepening. We adopted this,
  with per-repository clone and mining timeouts.

---

## 3. System architecture

DSARP is organized as a **graph of thirteen loops** (acquisition → mining → refactoring extraction →
tool evidence → graph construction → smell/refactoring alignment → dataset generation → ranker
training → inference → candidate ranking → recipe generation → human review → evaluation). Concretely
it is a Python package (`dsarp/`) with replaceable, interface-driven modules:

```
repositories/  mining/  tools/(arcan,designite)  smells/  graphs/  source_index/
evidence/  alignment/  features/  dataset/  candidates/  ranking/  training/(ranker,neural,lora)
agents/(explainer)  models/(providers)  openrewrite/  validation/  splits/  inference/(unseen)
reporting/  insights/  db/(sqlite)  api/(fastapi)  export/  pipeline.py  cli.py
```

Every module exchanges four Pydantic/JSON-Schema objects: **EvidenceCase** (input), **Suggestion**
(output), **ContextPackage** (token-optimized LLM input), and **HGRSReview** (human feedback).

---

## 4. Methodology in detail

### 4.1 Repository acquisition and history mining

Repositories are cloned with the Git CLI. For refactoring mining we require history, obtained via a
bounded fresh shallow clone (`git clone --depth N`, default N=500). Training repositories are the
canonical set — Apache Tika, Log4j2, Struts, Lucene, Commons-Lang/Collections/IO/CLI/Text, Maven,
Google Guava, Spring Framework — with **Apache Cassandra excluded** (§5). All clones live under
`data/raw/repos/` and are never read wholesale; the system operates on the source index and graph.

### 4.2 Refactoring extraction — RefactoringMiner

**Tool.** RefactoringMiner 3.1.4 (Tsantalis et al., *IEEE TSE*), a widely-used, high-precision tool
that detects 90+ refactoring types by AST-differencing consecutive commits.

**Invocation.** The Gradle launcher builds a classpath of 120 JARs that exceeds the Windows command
line limit, so we invoke the JVM directly with a wildcard classpath:

```
java -Xmx6g -cp "lib/*" org.refactoringminer.RefactoringMiner -a <repo> <branch> -json <out>
```

run from the tool directory (relative classpath) with Windows-style absolute paths for the repo and
output. Runs are bounded by a per-repository timeout; failures never fabricate events.

**Parsing.** The JSON output is parsed into a normalized `RefactoringEvent` (type, commit SHA, before/
after entity, file paths, and the *package-level* components inferred from file paths).

**Architectural filter (key design choice).** RefactoringMiner reports both architectural and
code-level refactorings. We keep only **architectural** ones — `Move Class`, `Move/Rename Class`,
`Extract Class/Subclass/Superclass`, `Extract Interface`, `Move/Pull-Up/Push-Down Method`,
`Move Attribute`, and package-level moves — and **discard code-level** ones (`Extract Method`,
`Rename Method`, `Change Access/Modifier`, `Extract Variable`, …). A commit containing only code-level
refactorings therefore contributes no training signal. This makes the learned model a model of
*architectural* change, aligned with the smells we target.

*Empirically*, recent commits skew heavily to code-level edits (e.g., 2,325 `Change Method Access
Modifier` across the Commons repos), whereas architectural refactorings are rarer and require deeper
history — motivating the depth parameter.

### 4.3 Smell detection

DSARP detects the common architectural smell catalogue **without requiring a JVM smell tool**, and can
additionally *import* Arcan/Designite results when available.

**Structural detector** (`smells/detector.py`), computed from the dependency graph and source index
with **repository-independent, median-relative thresholds**:

- **Cyclic Dependency** — components lying on a real directed cycle (NetworkX `simple_cycles`, bounded
  by `islice` to avoid exponential enumeration on dense graphs).
- **Hub-Like Dependency** — high fan-in *and* fan-out, thresholded at `max(5, 2×median(fan_in+out))`.
- **Unstable Dependency** — instability > 0.7 with fan-in ≥ 3 (a depended-upon yet unstable component).
- **God Component** — a package whose class count is ≥ `max(20, 3×median)` of its peers.

**Tool adapters** (`tools/arcan.py`, `tools/designite.py`). Two execution modes behind one interface:
*import mode* parses the tool's CSV/JSON export; *execute mode* runs the configured JVM command,
records provenance (command, status, logs), and — critically — **emits no evidence on failure**
(no fabrication). Arcan (Fontana et al.) and DesigniteJava (Sharma et al.) detect additional smells
(unstable/hub-like dependency, cyclic dependency, god class, etc.).

**Normalization.** The `EvidenceNormalizer` merges findings that describe the same smell on the same
components across sources; multi-tool agreement raises confidence and is recorded in `tool_sources`.

### 4.4 Dependency-graph construction and metrics

A package-level directed graph (`networkx.DiGraph`) is built from **import edges** derived by the
source indexer (or from a tool-provided graph). Per node we compute fan-in, fan-out, **Martin's
instability** *I = Ce/(Ca+Ce) = fan_out/(fan_in+fan_out)*, and **betweenness centrality**; at the graph
level, cycles, strongly-connected components, and counts. We also produce **graph slices** — the
affected components plus their one-hop neighborhood — which is what feeds the UI and (in compact form)
the LLM, never the full graph (a token-economy decision).

### 4.5 Source indexing

`source_index/indexer.py` is a dependency-free, conservative regex parser for `.java` files (test
directories excluded). It extracts files, package declarations, class/interface/enum/record names,
method signatures, imports, a symbol→file map, and **package-level import edges** (the fallback
dependency graph). It is intentionally best-effort: unknown symbols are omitted, never guessed, and a
missing symbol is treated by validators as `requires_source_inspection`, not as proof of absence.
(tree-sitter can be substituted where higher fidelity is needed.)

### 4.6 Repository-independent feature engineering and name masking

The ranker must not learn project-specific identifiers. Each (smell, candidate) pair is encoded as a
**23-dimensional structural feature vector** (`features/extractor.py`, schema-versioned): cycle size,
fan-in/out, instability, centrality, coupling, cohesion, ATDI, severity, tool-agreement count, edge
confidence, categorical codes for candidate/component role/component type, estimated edges
removed/added, affected-component count, recipe applicability, source-inspection availability,
public-API risk, graph delta, risk, and catalogue rank. For LLM/instruction data, real names are
**masked** to `Component_A/B/C…` via a reversible `NameMasker`; real names are restored only at
explanation time. This is what makes leave-one-repository-out a meaningful test rather than
memorization. *(Note: `cohesion` and `ATDI` are currently placeholders (0.0) pending a deeper parse —
see §8.)*

### 4.7 Smell–refactoring alignment

Two aligners produce training labels:

- **Historical alignment** (`alignment/aligner.py`). Each (smell, architectural-refactoring) pair is
  scored by `same_component` (exact package overlap, dominant weight), `component_neighbourhood`
  (shared prefix), `smell_component_touched`, and `type_plausibility` (does this refactoring type
  plausibly fix this smell family). A pair is a positive label only when the refactoring actually
  touched the smelly component — i.e., a developer historically restructured exactly there.
- **Weak supervision** (`alignment/weak.py`). When RefactoringMiner is unavailable, positives are the
  *strongest* fixer per smell family (e.g., Extract Interface / Dependency Inversion for a real cycle),
  with the remaining catalogue candidates as negatives — so both classes exist. Confidence is capped
  below historical labels so real evidence dominates when both are present.

We deliberately do **not** assume every historical refactoring fixed a smell; the alignment confidence
encodes uncertainty.

### 4.8 Training-dataset construction

For each smell we generate the deterministic candidate set (§4.10), attach the feature vector, and
label via the aligners. Rows carry `project_id` and `split` (enabling repository-level and LORO
splits), are **de-duplicated** by (project, commit, refactoring type, entities, smell, candidate), and
masked. The current real dataset is **5,022 rows across 11 repositories (≈32 % positive)**.

### 4.9 Candidate generation

The LLM is **not** permitted to invent the action space. A deterministic catalogue
(`candidates/generator.py`) enumerates refactorings per smell family — e.g., Cyclic Dependency →
{Extract Interface, Dependency Inversion, Introduce Facade, Introduce Adapter, Move Class, Move
Method}; God Component → {Extract Class, Move Class, Move Method, Introduce Facade}. Each candidate is
annotated with a graph-delta estimate, risk, recipe applicability, and its structural features.

### 4.10 Ranking models

`ranking/ranker.py` fuses a deterministic score, a learned model score, and evidence confidence. The
learned backend is loaded from `data/models/ranker.pkl` as `{model, metadata}`; inference only requires
`predict_proba`. Backends: gradient-boosted trees, LightGBM, RandomForest, a deterministic fallback,
and the neural ranker (below). Training (`training/ranker_trainer.py`) enforces the leakage guard,
supports **leave-one-repository-out**, exports feature importance, and emits an overfitting warning if
train ≫ validation. The final production model is trained on all training repositories; LORO folds are
non-persisting (a bug we fixed — folds previously overwrote the deployed model).

### 4.11 Grokking-informed neural ranker

`training/neural_ranker.py`. A small MLP (64→32) with ReLU, sigmoid output, **AdamW weight decay**
(the grokking-relevant regularizer), trained up to 3,000 epochs. Generalization is tracked at the
**repository level** every epoch (train accuracy on 10 repos vs held-out-repo accuracy) — the
"grokking curve" — and the best-held-out checkpoint is kept. Training uses PyTorch; **inference is a
pure-NumPy forward pass** (`NumpyMLP`), so the deployed model is fast and torch-free. Standardization
statistics are stored with the model.

### 4.12 LLM explanation (token optimization)

`agents/explainer.py` builds a minimal **ContextPackage**: stable policy references (Level 0) + the
evidence slice for one smell/candidate (Level 2); raw logs and full graphs are excluded (Level 3,
on-demand only). A `TokenBudgetManager` enforces an input-token budget, and a content-hash cache
suppresses duplicate calls (identical context + model ⇒ cached response). Providers
(`models/providers.py`) are pluggable: **offline** (deterministic, network-free default), **Ollama**,
**llama.cpp**, OpenAI-compatible, and **vLLM** (HPC). No cloud API is required.

### 4.13 No-hallucination validation and the accuracy gate

Eight validators (`validation/validators.py`) run after generation and around LLM output; they can
only *demote* claims, never fabricate support: output-schema, evidence-ID, file-existence,
entity-existence (against the source index), dependency-edge (against the graph), tool-finding,
recipe-applicability, and recipe-validation-status. Unverifiable entities become
`requires_source_inspection`. A configurable **accuracy gate** then emits only suggestions that are
valid (no unsupported claims), evidence-backed, and above a confidence threshold. The LLM never
overrides the validators.

### 4.14 OpenRewrite recipe generation

For automatable refactorings (e.g., Move Class, Extract Interface) we emit **draft** OpenRewrite YAML
or Java-visitor plans; design-heavy refactorings get a manual plan. A recipe is marked `validated`
**only** if an actual OpenRewrite dry-run plus Maven build pass — otherwise it stays `draft`/`failed`
with the reason recorded. We never claim validation we did not perform.

---

## 5. Experimental setup

- **Training repositories:** 11 open-source Java projects (above).
- **Held-out unseen test:** **Apache Cassandra**, never used in training, tuning, ranking, or
  validation. A `SplitManager` leakage guard refuses to run if Cassandra (or any unseen repo) appears
  in a training split, and it caught a real configuration bug during development.
- **Validation protocol:** **Leave-one-repository-out (LORO)** — train on 10 repositories, evaluate on
  the 11th, repeated for each. This is a *repository-level* split, not a random-row split, and is the
  correct test of cross-project generalization.
- **Metric:** classification accuracy of the candidate-preference labels at threshold 0.5 (baseline
  ≈0.68 given the positive rate). Grounding pass rate and hallucination count measure output safety.
- **Reproducibility:** the full local pipeline runs offline via `dsarp-local demo full`; 25
  unit/integration tests validate schema conformance, leakage prevention, masking, and end-to-end
  behavior.

---

## 6. Results (current)

| Quantity | Value |
|---|---|
| Training repositories | 11 (Cassandra held out) |
| Real training rows (architectural-only) | 5,022 (≈32 % positive) |
| Repositories with real historical labels | 9 (Guava, Lucene: structural-only — mining timed out) |
| LORO — gradient-boosted trees | 0.9535 |
| **LORO — grokking neural ranker (deployed)** | **0.9779** |
| Larger MLPs (128,64) / (128,64,32) | 0.9745 / 0.9746 (worse) |
| Grounding pass rate (offline) | 1.00 (0 hallucinations) |
| Unit/integration tests | 25 passing |

**On grokking (honest finding).** The neural ranker's held-out accuracy rises *early* (≈0.90 by epoch
150, as train accuracy reaches 0.99) and peaks at 0.919 around epoch 500, then plateaus — there is
**no classic grokking jump** (val staying near-random then suddenly generalizing). This is expected:
grokking is documented on tiny algorithmic datasets, whereas ours is a 5k-row tabular problem with
informative features. Nonetheless, the *grokking training recipe* (weight decay + long training +
best-held-out checkpoint) produced the best model, improving LORO by 2.4 points over trees. We report
this transparently rather than claiming the phenomenon.

---

## 7. Threats to validity

- **Weak-label determinism.** Where historical labels are absent (Guava, Lucene), weak labels are a
  graph rule; a model can fit them almost perfectly, inflating LORO. The real-label repositories are
  the trustworthy signal.
- **Alignment precision.** Within a single project all packages share a root prefix, which can inflate
  the neighbourhood feature; positives are nonetheless gated on exact component overlap.
- **Placeholder features.** `cohesion` and `ATDI` are currently 0.0 (no deep parse), so the feature
  space is narrower than the schema suggests.
- **Metric.** Accuracy at 0.5 is a proxy for ranking quality; top-k recall against held-out historical
  refactorings and human HGRS scores are stronger and are supported but not yet run at scale.
- **Source fidelity.** The regex indexer is conservative; some entities may be missed (handled safely
  as `requires_source_inspection`).

---

## 8. Improvement roadmap

1. **Robust bounded mining.** Kill the whole process tree on subprocess timeout (a large repo escaped
   its timeout and ran ~7.75 h) and guard graph metrics on very large graphs; then cleanly re-mine
   Guava and Lucene for real architectural labels.
2. **Richer, precise features.** Compute real **cohesion** (e.g., LCOM) and **ATDI**; add class-level
   graphs from the source index; tighten alignment to graph-adjacency rather than name prefix.
3. **Stronger labels.** Deepen history to capture more architectural refactorings; incorporate
   `Extract And Move Method` weighting; add human **HGRS** feedback as gold labels and close the loop
   into dataset/ranker updates.
4. **Model.** Because larger MLPs did not help, invest in *label quality and features* over capacity;
   optionally add a pairwise/learning-to-rank objective and calibrated confidence.
5. **Agentic operation.** A goose-style autonomous loop (generate → rank → explain → validate →
   refine-until-valid) exposed as an MCP server; and **SkillOpt**-style optimization of the policy
   "skill" files from validator/HGRS feedback (skills as trainable text, validation-gated edits).
6. **Recipe validation at scale.** Wire OpenRewrite dry-run + Maven build/tests in CI to move recipes
   from `draft` to `validated`, and re-analyze the graph to confirm smell reduction.
7. **Evaluation.** Report top-k recall vs held-out history and mean HGRS per smell/refactoring type;
   run the full unseen Cassandra evaluation and a no-hallucination leaderboard across providers.
8. **Optional LoRA.** Fine-tune the local explanation model on masked instruction data once the corpus
   exceeds the guarded threshold.

---

## 9. Tooling summary

| Tool / library | Role | How used |
|---|---|---|
| **RefactoringMiner 3.1.4** (Tsantalis et al.) | Mine refactorings from git history | `java -cp lib/* … -a <repo> <branch> -json`; architectural-only filter |
| **Arcan** (Fontana et al.) | Architectural smell detection | Optional import/execute adapter; provenance recorded |
| **DesigniteJava** (Sharma et al.) | Design/architecture smell detection | Optional import/execute adapter (CSV) |
| **OpenRewrite** (Moderne) | Automated refactoring recipes | Draft recipe generation; validated only on real dry-run+build |
| **NetworkX** | Dependency graph + metrics | Cycles, SCC, fan-in/out, instability, betweenness, slices |
| **scikit-learn / LightGBM** | Tree rankers | GradientBoosting/RandomForest/LightGBM backends |
| **PyTorch** | Neural ranker training | AdamW + weight decay; numpy inference after training |
| **Ollama / llama.cpp / vLLM** | Local LLM explanation | Pluggable providers; offline default |
| **Pydantic + JSON Schema** | Contracts | EvidenceCase / Suggestion / ContextPackage / HGRSReview |
| **Streamlit / FastAPI / SQLite** | UI / API / persistence | 20-page dashboard, 11-endpoint API, cross-session store |
| **Git** | History acquisition | Bounded fresh shallow clones (`--depth N`) |

---

## 10. Selected references

- N. Tsantalis, A. Ketkar, D. Dig. *RefactoringMiner 2.0*, IEEE Transactions on Software Engineering.
- F. Arcelli Fontana et al. *Arcan: architectural smell detection.*
- T. Sharma et al. *DesigniteJava: design smell detection for Java.*
- R. C. Martin. *Agile Software Development: Principles, Patterns, and Practices* (instability metric).
- A. Power, Y. Burda, H. Edwards, I. Babuschkin, V. Misra. *Grokking: Generalization Beyond Overfitting
  on Small Algorithmic Datasets*, 2022.
- Moderne. *OpenRewrite* — automated, type-aware source refactoring.
- Block. *goose* — open, extensible agent (MCP). Microsoft Research. *SkillOpt* — agent skills as
  trainable parameters.

*This report reflects the implemented system; claims are limited to what the code and experiments
support. See `docs/SHOWCASE.md` to run the system and `data/memory/current_status.md` for build state.*
