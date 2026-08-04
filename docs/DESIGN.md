# DSARP Evidence-Based Refactoring Agent — Design

This document is the compact, stable design reference. It is deliberately short (token policy).
See `docs/schemas/` for the authoritative JSON contracts and `dsarp/` for the implementation.

---

## 1. Final architecture (layers)

```
                        ┌──────────────────────────────────────────┐
                        │  UI layer (Streamlit, 12 pages)           │
                        │  observe · analyse · score (HGRS) · report│
                        └───────────────▲──────────────────────────┘
                                        │ read-only over data/ + SQLite
┌───────────────┐   ┌──────────────────┴───────────────────┐   ┌──────────────┐
│ CLI adapters  │   │            Orchestration              │   │ Backend API  │
│ dsarp-local   ├──►│  pipeline.py  ·  loops (1..13)         │◄──┤ (optional)   │
│ dsarp-hpc     │   └──────────────────┬───────────────────┘   └──────────────┘
└───────────────┘                      │
   ┌───────────────────────────────────┼────────────────────────────────────┐
   │ core services (pure, interface-driven, replaceable)                     │
   │  repositories · mining · tools(arcan/designite) · graphs · evidence     │
   │  alignment · dataset · candidates · ranking · agents · openrewrite      │
   │  validation · evaluation · export                                       │
   └───────────────────────────────────┼────────────────────────────────────┘
   ┌───────────────────────────────────┼────────────────────────────────────┐
   │ cross-cutting: token layer (context packages, budget mgr, hash cache),  │
   │ project memory, config profiles (local/hpc), model providers            │
   └─────────────────────────────────────────────────────────────────────────┘
```

## 2. Graph-of-loops workflow

Canonical mermaid diagram lives in `CLAUDE.md`. Loops 1–13:

1 acquisition · 2 commit mining · 3 RefactoringMiner · 4 tool evidence · 5 graph build ·
6 smell↔refactoring alignment · 7 dataset gen · 8 ranker/model training · 9 inference on new repo ·
10 candidate gen + ranking · 11 OpenRewrite recipes · 12 human review/feedback · 13 eval/reporting.

Training path = loops 1–8. Inference path = loops 9–13. Feedback (loop 12) re-enters loops 7–8.

## 3. Folder structure

Implemented as a `dsarp/` importable package (import-sane short name) mapping 1:1 to the
`core/*` module list in CLAUDE.md, plus `ui/`, `configs/`, `slurm/`, `scripts/`, `tests/`.
See repository tree.

## 4. Unified schemas

- Input evidence case → `docs/schemas/` + `dsarp.schemas.EvidenceCase`
- Suggestion output → `docs/schemas/suggestion_schema.json` + `dsarp.schemas.Suggestion`
- Context package → `docs/schemas/context_package_schema.json` + `dsarp.schemas.ContextPackage`
- HGRS review → `docs/schemas/hgrs_review_schema.json` + `dsarp.schemas.HGRSReview`

Every module, CLI, agent and provider exchanges these Pydantic models. Nothing else crosses a boundary.

## 5. Local execution plan (laptop)

SQLite + Streamlit + NetworkX + scikit-learn/LightGBM + local LLM (Ollama / llama.cpp / OpenAI-compatible).
`dsarp-local setup | repo clone | mine | tools import | graph build | dataset build | ranker train | suggest | ui`.
Heavy Java tools run in **import mode** (parse tool exports) so the laptop path never needs a JVM.

## 6. HPC execution plan (Slurm)

Batch mining, vLLM multi-GPU inference, optional LoRA. Slurm scripts under `slurm/`.
`dsarp-hpc mine batch | tools batch | dataset build --large | train ranker | train lora | serve model | evaluate`.
Same core code; only the config profile (`configs/hpc.yaml`) and providers differ.

## 7. UI design

12 Streamlit pages (Projects → Reports) as listed in CLAUDE.md. All pages are read-only over
`data/` and the SQLite store except Human Review (writes HGRS) and mining/train triggers.
Interactive graphs via pyvis/Plotly/NetworkX.

## 8. Training strategy

Mine real refactorings (RefactoringMiner) → align with parent-revision smell evidence using an
**alignment confidence score** (never assume a historical refactoring fixed a smell). Deterministic
candidate generator defines the action space; a local preference ranker (LightGBM/sklearn) learns
ordering; LLM only explains ranked candidates. Optional LoRA on HPC. MVP works without LoRA.

## 9. Cassandra test plan

`apache/cassandra` is the **only** unseen repo — never used in train/tune/rank/LoRA/validation.
Inference path 9–13 + report: smell/suggestion counts, evidence-grounding pass rate, hallucination
failures, JSON validity, recipe draft/validation counts, runtime, tokens, HGRS if reviewed.

## 10. Implementation milestones

M1 schemas+config (done) · M2 repo manager · M3 RefactoringMiner adapter · M4 Arcan/Designite adapters ·
M5 graph builder · M6 evidence normalizer · M7 dataset builder · M8 candidate generator · M9 ranker ·
M10 local LLM agent · M11 OpenRewrite generator · M12 validators · M13 UI · M14 local runner ·
M15 HPC Slurm · M16 Cassandra eval.

Status: **complete MVP across M1–M16** — SQLite backend, source index, graph slices, multi-repo
dataset + LORO ranker, unseen-repo inference, OpenRewrite validation, FastAPI backend, 20-page UI,
`demo full`, HPC Slurm set + guarded submit, 23 tests. Java tool *execution* is wired (config-driven
subprocess) but emits no evidence without the real binaries (no fabrication); import mode is default.

### Added modules (continuation)

`dsarp/db` (SQLite) · `dsarp/source_index` · `dsarp/splits` (leakage guard, LORO) ·
`dsarp/features` (repo-independent features + NameMasker) · `dsarp/training` (ranker_trainer, lora) ·
`dsarp/dataset/multi_repo` · `dsarp/inference/unseen` · `dsarp/reporting/generalisation` ·
`dsarp/insights` · `dsarp/api` (FastAPI) · `dsarp/openrewrite/validator` · `dsarp/models/manager` ·
`dsarp/tools/runner` · `dsarp/demo`. Docs: `api_contract.md`, `inter_agent_protocol.md`,
`GENERALISATION_REPORT.md`, `FINAL_MVP_STATUS.md`, `IMPLEMENTATION_GAP_REPORT.md`; `examples/*.json`.
