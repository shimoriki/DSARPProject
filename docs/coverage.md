# Smell coverage, and what is actually verified

Read from `dsarp/refactoring/agents.py`, which is the live registry: `cli.py`, `multiagent.py`,
`iterative_loop.py` and `openrewrite_loop.py` all import it. The table in
`strategies.STRATEGIES` is **not** live — `strategies.plan_for` is called only from inside its own
module, and it still declares as "not automatable" four smells the agents do plan. An audit that
reads `strategies.py` alone understates coverage.

## Coverage: 13 of 15 smell types have a planner

| smell | planner | operation |
|---|---|---|
| Cyclic Dependency | the loop / `move_planner` | move class, invert edge, merge package |
| Hub-Like Dependency | `plan_god_component` | split package |
| God Component | `plan_god_component` | split package |
| Feature Concentration | `plan_god_component` | split package |
| Scattered Functionality | `plan_scattered_functionality` | merge package |
| Unstable Dependency | `plan_unstable_dependency` | invert dependency |
| Deficient Encapsulation | `plan_deficient_encapsulation` | `ReduceFieldVisibility` |
| Unutilized / Unnecessary Abstraction | `plan_unutilized_abstraction` | delete or inline the unused type |
| Multifaceted Abstraction | `plan_extract_class` | `ExtractStaticHelpers` |
| Insufficient Modularization | `plan_extract_class` | `ExtractStaticHelpers` |
| Missing Hierarchy | `plan_introduce_supertype` | `IntroduceSupertype` |
| Wide Hierarchy | `plan_introduce_supertype` | `IntroduceSupertype` |
| Rebellious Hierarchy | `plan_extract_interface` | `ExtractInterfaceForClass` |
| Broken Modularization | `plan_broken_modularization` | member relocation |
| **Broken Hierarchy** | refused | replacing inheritance with delegation rewrites the public API and every call site |
| **Dense Structure** | refused | density is a property of the whole system; no local refactoring reduces it |

Coverage has not been the limiting factor for some time. What follows is.

## What the findings actually are

2,275 findings over 20 repositories (`data/normalized/`). Every one is an architecture smell:

| smell | findings | share |
|---|---|---|
| Cyclic Dependency | 1,120 | 49% |
| Hub-Like Dependency | 628 | 28% |
| God Component | 329 | 14% |
| Feature Concentration | 80 | 4% |
| Scattered Functionality | 62 | 3% |
| Unstable Dependency | 54 | 2% |
| Feature Envy, Dense Structure | 2 | <1% |

The nine class-level smells in the table above — encapsulation, abstraction, hierarchy — have a
planner each and essentially no occurrences in this corpus. Building more of them would address
less than 1% of what the detectors report.

## Verified effectiveness, which is the real gap

| operation | share of findings | verified against bytecode? |
|---|---|---|
| move class / invert edge (Cyclic) | 49% | **yes** — 18 applied, 18 built, 18 removed their edge, 14 accepted on tests |
| split package (Hub-Like, God, Feature Concentration) | 46% | **predicted harmful**: 77 of 78 add edges, none reduces cycle participation |
| merge package (Scattered Functionality) | 3% | not measured |
| invert dependency (Unstable) | 2% | not measured |
| everything class-level | <1% | not measured |

No cycle has ever been dissolved — not by this system on pdfbox, log4j2 or tika, and not by the
authors of the Arcelli Fontana replication package in either of their two hand-refactored trees.
The defensible claim is elimination of a **named package edge** with its cost measured, not smell
removal.

## Why the split result matters more than new operations

`plan_god_component` covers 1,037 findings. Splitting a package removes the smell it targets — a
smaller package is no longer a God Component — while the dependency graph gets worse. Commons
Compress's hand-written `noModularity` tree measured 108 → 162 package edges and 28 → 38
packages-in-cycles, and this project's own prediction over 78 applicable splits agrees in
direction on 77 of them.

Two real metrics, pointing opposite ways on the same change. That is a question about which one
the product optimises, and no additional recipe answers it.
