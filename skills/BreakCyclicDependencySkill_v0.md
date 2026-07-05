# BreakCyclicDependencySkill_v0

Reusable agent skill for proposing refactorings that break cyclic dependencies
between software components (packages, modules, classes, or services).

## When this skill applies
The smell case has `smell_type: Cyclic Dependency` (or an equivalent custom
tool label) with two or more affected components.

## Procedure

1. **Restate the cycle from evidence only.** List the affected components and
   every dependency edge among them that appears in `dependency_evidence`,
   citing its `evidence_id`. Never invent an edge or a direction.
2. **Find the weakest edge.** Prefer breaking the edge with the lowest
   weight/confidence, the fewest co-changes, or the one that contradicts the
   intended layering. If edge weights are unavailable, say so and mark the
   boundary as `requires_source_inspection`.
3. **Choose one primary refactoring** from this ordered preference list:
   - **Dependency Inversion** – introduce an abstraction owned by the more
     stable component; the less stable component implements it.
   - **Extract Interface** – when only a narrow API of the target is used.
   - **Move Class / Move Method** – when a small set of elements clearly
     belongs on the other side of the boundary.
   - **Split Component** – when a component serves two unrelated roles that
     drag it into the cycle.
   - **Facade / Adapter** – when many scattered call sites must be decoupled
     behind a single entry point.
4. **Write 3–7 concrete, ordered implementation steps.** Each step names the
   component(s) it touches. Steps must be independently verifiable (compile,
   run tests, re-run the dependency analysis).
5. **State risks and trade-offs explicitly** — at least one. Typical: behavior
   drift during moves, widened public API, added indirection, build breakage
   in downstream modules.
6. **State assumptions and open questions** whenever evidence is missing,
   and add "Requires source inspection." for any claim about exact classes,
   methods, or call directions that the evidence does not contain.
7. **Keep the change minimal.** Prefer the smallest edit that removes the
   cycle over broad rearchitecture. Do not propose renaming or reformatting
   unrelated code.

## Output constraints
- Return only the required JSON object; every factual claim about components
  or edges must cite an `evidence_id` from the case.
- `confidence` must reflect evidence completeness: cap at 0.6 when any edge
  direction in the proposed boundary is not supported by evidence.
- Expected benefit should reference the measurable effect: cycle removed,
  reduced coupling, restored acyclic layering.
