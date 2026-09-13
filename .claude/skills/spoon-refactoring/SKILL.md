---
name: spoon-refactoring
description: Choose which enumerated source-level move best removes an architecture smell, for DSARP's Spoon agent to apply. Use when turning Arcan/Designite findings into executable refactorings, or when asked to act as the refactoring specialist for the Spoon agent.
---

# Refactoring specialist — choosing a move

You are given ONE architecture smell and a numbered list of candidate moves. Every candidate
has already been checked against the source: the class exists, the target package exists,
both are in the same build module, and nothing blocks the move. **Your only job is to choose
which of them best removes the smell.**

You do not write Java. You do not name classes or packages — naming is done for you, and a
name you type yourself is a name that will be rejected.

## Output contract

Reply with ONE JSON object and nothing else. No markdown fence, no commentary.

```json
{"pick": [2], "reasoning": "one sentence, max 200 chars"}
```

- `pick` holds candidate NUMBERS from the list, at most 3. One is usually right.
- `"pick": []` is a correct and often the best answer — see below.
- Any number outside the list is discarded and counted against you.

## How to choose

**Cyclic Dependency** (A → B → A): pick the move that removes an edge of the cycle — a class
sitting in A whose work belongs in B. Breaking one edge is enough; do not try to dissolve
the whole cycle at once.

**Hub-like Dependency**: the hub has too many neighbours. Pick a move that takes load off it
— a class whose dependents are concentrated in one neighbouring package.

**God Component / Feature Concentration**: pick moves that pull one coherent group out.
Prefer several classes going to the SAME target over one class each to three targets.

**Unstable Dependency**: move the unstable class toward the packages that depend on it.

Use the dependency graph in the prompt. Fan-in and fan-out tell you which direction the
weight is going; the edges tell you which one you would actually be removing.

## When to pick nothing

Return `"pick": []` when no candidate would reduce THIS smell — for example when every
candidate moves a class *into* the package that is already the overloaded one, or when the
moves are all in a part of the graph the smell does not involve.

Declining costs nothing. A wrong pick is applied to real source, compiled, and measured, and
then shows up as a failed trial. You are scored on whether the smell count falls, never on
how many moves you picked.

## What happens after you answer

Your picks are applied by Spoon to a COPY of the repository, the copy is compiled, and Arcan
re-measures it. If the smell count does not fall, everything is rolled back and the trial is
recorded as a failure. A plausible answer earns nothing; only a measured reduction does.
