# DSARP — evidence-based architectural refactoring

DSARP takes a Java repository, finds its architectural problems with real analysis tools,
**actually rewrites the source** to fix them, then **re-runs the same tools** to check whether
the problems really went away.

That last step is the point. Plenty of tools suggest refactorings. DSARP measures whether its
suggestions worked, and refuses to call anything a success unless the rewritten code still
compiles and a real tool confirms the improvement.

```bash
py -m dsarp.cli refactor-openrewrite --repo-url https://github.com/apache/commons-validator --detector both
```

---

## The idea in one picture

```
   ┌─────────┐   ┌──────┐   ┌──────────┐   ┌───────────┐   ┌─────────┐
   │ DETECT  │──▶│ PLAN │──▶│ REFACTOR │──▶│ RE-DETECT │──▶│ COMPARE │
   └─────────┘   └──────┘   └──────────┘   └───────────┘   └─────────┘
    Arcan +      one agent   OpenRewrite     the SAME       per-smell
    Designite    per smell   rewrites the    tools, on      before/after
    (real jars)  family      real source     the new code
```

Every box is a real subprocess: `java -jar arcan.jar`, `java -jar DesigniteJava.jar`,
`mvn rewrite:run`. Nothing is simulated.

---

## Step by step

### 1. Detect — what is actually wrong?

Two independent tools, because they see different things:

| tool | reads | finds |
|---|---|---|
| **Arcan 1.2.1** | compiled bytecode | package-level Cyclic, Unstable and Hub-Like Dependency |
| **DesigniteJava** | source | God Component, Scattered Functionality, and 10 design smells |

Arcan needs bytecode, so DSARP runs `mvn compile` first and points it at `target/classes`.
That detail matters later: **if the code does not compile, Arcan cannot measure anything.**

### 2. Plan — one agent per architectural concern

Each finding is routed to exactly one agent, and every agent must return a plan for every
finding it receives — either a real refactoring or an explicit reason it cannot be automated.
Nothing is silently dropped.

| agent | concern | smells it owns |
|---|---|---|
| `DependencyAgent` | coupling direction | Cyclic, Unstable, Hub-Like |
| `ModularizationAgent` | package size and cohesion | God Component, Scattered Functionality |
| `EncapsulationAgent` | information hiding | Deficient Encapsulation |
| `AbstractionAgent` | abstraction quality | Unutilized / Unnecessary / Multifaceted |
| `HierarchyAgent` | inheritance structure | Missing / Wide / Rebellious / Broken Hierarchy |
| `StructureAgent` | system-wide | Dense Structure |

### 3. Refactor — real OpenRewrite recipes

Plans compose into one `rewrite.yml` and run as a single `mvn rewrite:run`. Most entries are
stock OpenRewrite recipes; three are ours, in `tools/dsarp-recipes/`, because stock cannot
express them declaratively:

- `ReduceFieldVisibility` — there is no stock field-visibility recipe at all
- `ExtractInterfaceForClass` — stock ships this only as a *visitor*, unusable from YAML
- `IntroduceSupertype` — same, for giving a group of classes a shared new interface

**Four safety preconditions**, every one discovered from a real broken build:

1. A relocated class loses its same-package references, so the needed imports are written in
   first. (OpenRewrite's `AddImport` cannot do this — it inspects the file while it is still
   in the old package and concludes no import is needed.)
2. A class using package-private types or members is never moved; no import can restore that
   access, and widening visibility would change the public API.
3. Package merges are rejected on same-name collisions, or when the source package has
   sub-packages.
4. Two refactorings touching the same type in one pass are separated.

### 4. Re-detect and compare — did it work?

The same tools run again on the rewritten code. Results are reported **per smell type**, split
into what was targeted and what moved as a side effect.

> **Read the targeted delta, not the grand total.** Splitting a God Component creates a new
> package, which Designite then flags as Feature Concentration. A refactoring that removed
> exactly what it aimed at can still make the overall count look worse.

---

## Why you can trust the numbers

Three times during development a change *looked* like a large win and was actually a
**measurement failure**. Each is now a permanent guard:

| the claim | what was really happening | the guard |
|---|---|---|
| Arcan `20 → 0` | the code never compiled, so Arcan had no bytecode to read | no bytecode ⇒ `UNMEASURABLE`, not zero |
| `13.2%` reduction | build broke, Arcan dropped out, score recomputed over fewer tools | accepting a pass requires a **compiling build** |
| an LLM proposed a deletion | the class was still referenced — its own reasoning said so | closed loop returned `rejected`; a pre-check now refuses it |

**A measurement failure is never scored as a success.** That rule is the core contribution.

---

## Getting started

```bash
py -m pip install -e .[local]                 # Python side
mvn -f tools/dsarp-recipes/pom.xml install    # build DSARP's custom recipes
py -m streamlit run ui/streamlit_app.py       # dashboard at localhost:8501
showcase.bat                                  # guided 8-step demo (Windows)
```

External tools (Arcan, Designite, Maven) are **not committed** — see
[docs/SETUP_TOOLS.md](docs/SETUP_TOOLS.md). Anything missing is reported as unavailable rather
than silently skipped.

### Common commands

```bash
# one pass: detect -> refactor -> verify
py -m dsarp.cli refactor-openrewrite --repo <name> --detector both

# repeat until it stops helping (rolls back any pass that breaks the build)
py -m dsarp.cli refactor-iterative --repo <name> --max-passes 4

# ask an LLM for recipes on smells we cannot handle, then test them
py scripts/run_ai_recipes.py --repo <name> --execute
```

---

## Where things live

```
dsarp/
  tools/          run Arcan and Designite, parse their output formats
  refactoring/    agents.py     routing, one agent per concern
                  strategies.py the refactorings themselves
                  params.py     tunable thresholds (the tuning surface)
                  ai_recipes.py LLM-proposed recipes, validated then tested
  openrewrite/    generate rewrite.yml, run Maven
  verification/   openrewrite_loop.py  one pass
                  iterative_loop.py    repeat until it stops helping
tools/dsarp-recipes/   our custom OpenRewrite recipes (Java)
ui/pages/              Streamlit dashboard
docs/MVP_RESULTS.md    scope and measured results
```

---

## Scope

Five smell types have an automated, compile-safe refactoring: Cyclic Dependency, Unstable
Dependency, God Component, Deficient Encapsulation, Missing/Wide Hierarchy.

The rest are reported with the specific reason they are not automatable — most need
member-level extraction with real type attribution, which means rebuilding the source index on
OpenRewrite's LST. Details and measured results: [docs/MVP_RESULTS.md](docs/MVP_RESULTS.md).

## The learning side

DSARP also learns to *rank* suggestions, from real refactoring history mined with
RefactoringMiner across 17 repositories, using repository-independent structural features and
leave-one-repository-out validation. Log4j2 is held out as the unseen benchmark. This is an
evaluation artifact rather than part of the refactoring critical path — see
[docs/DESIGN.md](docs/DESIGN.md) and [CLAUDE.md](CLAUDE.md) for the governing no-hallucination
policy.
