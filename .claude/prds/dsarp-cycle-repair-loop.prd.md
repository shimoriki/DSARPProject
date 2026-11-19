# DSARP Cycle-Repair Loop

## Problem
Researchers and maintainers of large Java systems can detect architectural cycles, but cannot get a
refactoring that demonstrably removes one. Existing tools stop at recommendations, or report smell
counts that move for unrelated reasons. Without a trustworthy loop, automated architectural
refactoring cannot be evaluated at all.

## Evidence
- A label-based recommender reached 0 of 120 target smells removed (project ledger).
- Planned moves removed their named edge 18 of 18 times; tests accepted 14 (project status, 2026-09-23).
- No cycle has been dissolved on pdfbox, log4j2 or tika, nor by experts in two hand-refactored trees.
- One Log4j2 small cycle group is predicted dissolvable by one move. Assumption — needs validation
  via the spike in Milestone 2.
- Maintainer demand for such moves: Assumption — needs validation via review of accepted patches.

## Users
- **Primary**: the thesis author and examiners, who need defensible, reproducible evidence of what
  automated architectural refactoring achieves.
- **Secondary**: architecture researchers reusing the measurement instrument.
- **Not for**: unattended production refactoring; non-Java systems; teams wanting a recommender only.

## Hypothesis
We believe **a deterministic, predicted-first repair loop aimed at small cycle groups** will **turn
detection into verified cycle removal** for **large Apache Java systems**.
We'll know we're right when **pre-registered targets on previously unused repositories reach
dissolved status with tests intact, beyond a placebo run**. A clean negative result still answers the
research question, and is an accepted thesis outcome.

## Success Metrics
| Metric | Target | How measured |
|---|---|---|
| Dissolved rate (Level 4c), by group size | TBD — needs validation via pilot, frozen before confirmatory run | Bytecode readers plus same detector |
| Shrunk rate (4b), edge rate (4a) | Reported, never relabelled as dissolved | Same |
| Prediction error on applied changes | Exact on the deciding edge; reported per candidate | Predicted vs measured |
| Placebo delta | Zero, or explained | Neutral edit through whole loop |
| Repeat-run agreement | Identical | Run twice |
| Harness correctness | Every known-answer case gets correct verdict | Known-answer suite |
| API effect | Rates reported with and without binary breaks | API comparison per candidate |
| Invalid runs | Reported; counted as not-success in denominator | Three-state verdict |

## Scope
**MVP** — One frozen protocol that reports, for fixed target groups on fixed repositories, how many
were dissolved, with tests, API status and placebo alongside.

**Out of scope**
- Transformer or classifier work — evidence closed it.
- Package splitting — predicted worse in 77 of 78 cases.
- A sixth smell-delta ranker — five failed held-out.
- Giant cycle dissolution — cost is out of reach; named-edge results only.
- LLM roles, generated tests, new operators — deferred until the decision point in Milestone 4.

## Delivery Milestones
<!-- Status: pending | in-progress | complete -->

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | Consolidated baseline | All work on one pinned, backed-up line | pending | docs/FINAL_BUILD_PLAN.md |
| 2 | Spike | One real answer: does the predicted move dissolve its group? | pending | docs/FINAL_BUILD_PLAN.md |
| 3 | Trusted instrument | Known-answer suite passes; cross-module findings explained; placebo zero | pending | docs/FINAL_BUILD_PLAN.md |
| 4 | Group planner and pilot | Multi-move plans validated outside confirmatory repositories | pending | docs/FINAL_BUILD_PLAN.md |
| 5 | Confirmatory result | Pre-registered numbers, positive or negative | pending | docs/FINAL_BUILD_PLAN.md |

## Open Questions
- [ ] Which Arcan version produced `baseline_csv`, and may it be published?
- [ ] Would a maintainer accept a dissolve that breaks public API? Needs validation via patch review.
- [ ] Are the 104 cross-module findings real or merge artifacts?
- [ ] If moves alone dissolve little, promote new operators or report that as the finding?
- [ ] How many targets are feasible given test runtime? Needs validation via pilot.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Spike fails | Medium | High | Decide at Milestone 2 before building more |
| Late-found measurement bug | High, by project history | High | Known-answer suite before freezing protocol |
| Tuning leaks into results | Medium | High | Confirmatory repositories unused so far |
| Small-group selection bias | High | Medium | Fixed selection rule; no generalizing to tangled cores |
| Silent behavior change | Medium | High | Dispatch-order comparison plus tests |
| Work lost on one disk | Medium | High | Back up first |
| Test runtime limits sample | High | Medium | Cheap checks first; tests only for survivors |

---
*Status: DRAFT — requirements only. Implementation plan in docs/FINAL_BUILD_PLAN.md.*
