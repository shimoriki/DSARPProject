# Architectural RefAgent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A RefAgent-style multi-agent loop that plans and applies architectural refactorings, removing package cycles in real Java projects. Every result passes the same deterministic gates as the existing beam-search arm and is compared with that arm on the same frozen targets.

**Architecture:** RefAgent's four roles are kept and retargeted from one class to one package cycle.
- **Planner:** an LLM that proposes operations from a fixed catalogue.
- **Generator:** the existing deterministic engines that write those operations.
- **Compiler agent:** an LLM that repairs build failures.
- **Tester agent:** an LLM that repairs test regressions.

The two repair agents are scoped to the main-source files the plan touched. A fifth role, the architecture judge, stays deterministic: the existing gates, ArchUnit, Arcan and japicmp. When the judge says a plan does not remove the cycle, that result goes back to the planner. This is the architectural feedback RefAgent lacks.

**Tech Stack:** Python 3.13 (`py`), pytest, the existing `dsarp` package, Spoon (`tools/dsarp-spoon`), Maven, an OpenAI-compatible model endpoint through `dsarp/models/providers.py`.

**Spec:** No separate spec. This plan's Architecture and Global Constraints stand in for one. Sources it argues from:
- RefAgent: Oueslati, Lamothe, Khomh, arXiv 2511.03153 (2025). Planner, generator, compiler agent and tester agent; up to 20 feedback rounds per loop; pass rates level off near 12 rounds; GPT-4o, StarCoder2-15B and DeepSeek-Coder-33B; one class at a time; method-level refactorings.
- `docs/superpowers/specs/2026-11-02-mixed-operator-cycle-repair-design.md`: operators, the 5-round repair budget (D5), repaired runs as a separate arm (D6), the model warning (D7), and anti-goals.

**Departure the user asked for:** that spec says "LLM only as scoped repair, never as planner or judge". Here the LLM is also the planner. It stays out of judging. The LLM-planned arm is frozen and compared with the beam arm, so its value is measured rather than assumed.

## Global Constraints

- The LLM never judges. Acceptance is `gates.decide()` plus the level from `scc_planner.level()`, exactly as in `scc_dissolve.measure`.
- Plans are frozen in `preregistration.json` before anything is applied. Repair may change code; it may not change the plan.
- LLM edits may touch only main-source `.java` files the plan's apply step changed. They never touch `src/test/**`, `pom.xml`, `*.gradle`, `META-INF/**` or files outside the working copy.
- An LLM edit may not add `Class.forName(`, `ServiceLoader`, `MethodHandles.` or `.newInstance(` (the same list as `gates.REFLECTIVE`).
- The operation catalogue is `moveClass` and `invertEdge` only, the operators the engines already apply.
- Every class or package the planner names must already exist in the baseline jdeps graph, as a top-level fully qualified name.
- Planner rounds per target: 3. Repair budget per failure stage: 5 rounds (spec D5). Both are CLI flags.
- Targets come from an existing beam-arm `preregistration.json` (`--targets-from`), so both arms are compared on identical cycles.
- Model access only through `LocalProvider(model, base_url, api_key=...)`. No new SDK dependency. The key is read from the environment variable named by `--api-key-env`.
- Arm record: `{"engine", "facades", "operators": "mixed", "repair": False, "planner": "llm", "model": <name>}`. The repair budget is recorded per row, and repaired runs write `rows_repair.jsonl` so the two arms stay separate (spec D6).

## Review Focus

1. **The model wraps its JSON in prose or a ```json fence.** `parse_ops` should take the first JSON object and still work (Task 3).
2. **The model names a nested (`A$B`) or simple class name.** The operation should be rejected as `unknown class` and the reason fed back (Task 3).
3. **The model endpoint is down or times out.** That target should be recorded with `moves=[]` and `why` starting `model call failed`, and the run should continue (Task 3).
4. **A repair edit's search text matches 0 or 2+ times.** The edit should be refused and the reason fed back the next round (Task 5).
5. **A repair adds a reflective lookup to dodge a compile error.** The edit should be refused before it is written (Task 5).

---

## File Structure

| File | Responsibility |
|---|---|
| `dsarp/agentic/__init__.py` | Package marker |
| `dsarp/agentic/context.py` | The planner's view of one cycle: package edges, carrier class edges, rules, rendered as prompt text |
| `dsarp/agentic/planner.py` | Parse, validate and simulate LLM operations; the planner feedback loop |
| `dsarp/agentic/repair.py` | Error summaries, scoped search/replace edits, the compiler/tester repair loop |
| `dsarp/agentic/run.py` | CLI: freeze LLM plans on frozen targets, confirm them through `measure` |
| `dsarp/experiments/scc_dissolve.py` | Modify: apply mixed plans, an optional repair hook in `measure`, `arm_matches` |
| `tests/test_agentic_context.py`, `tests/test_agentic_planner.py`, `tests/test_agentic_repair.py`, `tests/test_agentic_run.py`, `tests/test_scc_dissolve_apply.py`, `tests/conftest.py` | Tests, one file per task, plus the shared `Scripted` fake model |

Shared operation shape, used across tasks, identical to `scc_planner.plan`'s state: `Op = Tuple[str, str, str]`, either `("move", class_fqn, dest_pkg)` or `("invert", consumer_pkg, impl_fqn)`.

Shared plan dict, a superset of `scc_planner.plan`'s output: `{"component": List[str], "size": int, "moves": List[List[str]], "inversions": List[List[str]], "predicted_left": int, "dissolves": bool, "planner": "llm", "rounds": List[Dict]}`.

Shared fake model, in `tests/conftest.py`:

```python
class Scripted:
    def __init__(self, *texts): self.texts, self.prompts = list(texts), []
    def generate(self, prompt, **_):
        self.prompts.append(prompt); return Completion(text=self.texts.pop(0))
```

---

### Task 1: Apply mixed plans, and check arms, in `scc_dissolve`

**Files:**
- Modify: `dsarp/experiments/scc_dissolve.py` (`_apply` call in `measure` at line 237; arm check in `main` at lines 413-417)
- Test: `tests/test_scc_dissolve_apply.py`

**Interfaces:**
- Consumes: `_apply(copy, moves, work, engine)`, `mixed_plan.to_edits(inversions, moves)`, `spoon_runner.apply_edits`, `spoon_runner.module_classpath`.
- Produces: `_apply_plan(copy: Path, plan_: Dict[str, Any], work: Path, engine: str) -> Dict[str, Any]` (same return shape as `_apply`); `_apply_inversions(copy: Path, edits: List[Dict], work: Path) -> Dict[str, Any]`; `arm_matches(frozen: Dict[str, Any], arm: Dict[str, Any]) -> bool`. `measure` calls `_apply_plan`.

- [ ] **Step 1: Write the failing tests**

```python
def test_apply_plan_moves_then_inverts(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(sd, "_apply", lambda c, m, w, e: calls.append(("moves", m, e)) or {"applied": True})
    monkeypatch.setattr(sd, "_apply_inversions", lambda c, edits, w: calls.append(("inv", edits)) or {"applied": True})
    plan = {"moves": [["p.A", "q"]], "inversions": [["q", "p.A"]]}
    assert sd._apply_plan(tmp_path, plan, tmp_path, "text") == {"applied": True}
    assert calls[0] == ("moves", [["p.A", "q"]], "text")
    assert calls[1][1][0]["type"] == "q.A"          # inversion names the moved class's new name

def test_apply_plan_stops_when_moves_fail(monkeypatch, tmp_path):
    monkeypatch.setattr(sd, "_apply", lambda *a: {"applied": False, "why": "x"})
    monkeypatch.setattr(sd, "_apply_inversions", lambda *a: pytest.fail("must not run"))
    assert sd._apply_plan(tmp_path, {"moves": [["p.A", "q"]], "inversions": [["q", "p.A"]]}, tmp_path, "text")["applied"] is False

def test_arm_matches_fills_old_defaults():
    arm = {"engine": "text", "facades": True, "operators": "moves", "repair": False}
    assert sd.arm_matches({"engine": "text", "facades": True}, arm)
    assert not sd.arm_matches({"engine": "spoon", "facades": True}, arm)
    llm = {**arm, "operators": "mixed", "planner": "llm", "model": "m"}
    assert not sd.arm_matches(arm, llm)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `py -m pytest tests/test_scc_dissolve_apply.py -v`
Expected: FAIL with `AttributeError: module ... has no attribute '_apply_plan'`

- [ ] **Step 3: Implement in `dsarp/experiments/scc_dissolve.py`**
  - `_apply_inversions` runs Spoon `apply_edits` per source root, grouping edits the way `_apply`'s Spoon branch does.
  - `_apply_plan` applies moves first with the chosen engine, then `to_edits(plan_.get("inversions") or [], plan_["moves"])` through `_apply_inversions`. An empty list means skip.
  - `arm_matches` returns `{"operators": "moves", "repair": False, **frozen} == arm`, the expression now inline in `main`.
  - `main` calls `arm_matches`, and `measure` calls `_apply_plan(copy, plan_, work, engine)`. Plans without `"inversions"` behave as before.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_scc_dissolve_apply.py tests/test_scc_planner.py -v`
Expected: PASS (existing planner tests unchanged)

- [ ] **Step 5: Commit**

```bash
git add dsarp/experiments/scc_dissolve.py tests/test_scc_dissolve_apply.py
git commit -m "Apply mixed plans in measure, and check arms in one place"
```

---

### Task 2: Planner context

**Files:**
- Create: `dsarp/agentic/__init__.py`, `dsarp/agentic/context.py`
- Test: `tests/test_agentic_context.py`

**Interfaces:**
- Consumes: `scc_planner.top_level_edges`.
- Produces: `build_context(edges: Set[Tuple[str, str]], comp: Set[str], max_carriers: int = 60) -> Dict[str, Any]` with keys:
  - `packages`: sorted;
  - `package_edges`: list of `[a, b, n_class_edges]`;
  - `carriers`: list of `[cls_a, cls_b]` crossing packages inside `comp`, at most `max_carriers`, ordered by package edge with the fewest carriers first;
  - `classes`: sorted top-level classes of `comp`.

  Also `render(ctx: Dict[str, Any], feedback: str = "") -> str` builds the prompt: catalogue, JSON output format, rules, context, then feedback last.

- [ ] **Step 1: Write the failing tests**

```python
EDGES = {("a.X", "b.Y"), ("b.Y", "a.Z"), ("b.W", "a.Z"), ("c.Q", "a.X")}

def test_context_keeps_only_cycle_edges():
    ctx = build_context(EDGES, {"a", "b"})
    assert ctx["packages"] == ["a", "b"]
    assert sorted(ctx["package_edges"]) == [["a", "b", 1], ["b", "a", 2]]
    assert ["c.Q", "a.X"] not in ctx["carriers"]

def test_context_caps_carriers_cheapest_edge_first():
    ctx = build_context(EDGES, {"a", "b"}, max_carriers=1)
    assert ctx["carriers"] == [["a.X", "b.Y"]]

def test_render_states_catalogue_and_feedback():
    text = render(build_context(EDGES, {"a", "b"}), feedback="moveClass a.Q: unknown class")
    assert "moveClass" in text and "invertEdge" in text and '"operations"' in text
    assert text.rstrip().endswith("moveClass a.Q: unknown class")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `py -m pytest tests/test_agentic_context.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dsarp.agentic'`

- [ ] **Step 3: Implement `build_context` and `render` in `dsarp/agentic/context.py`**
  - The rules text names the constraints the validator enforces:
    - top-level fully qualified names only;
    - destination must be an existing package;
    - no moving into another module;
    - no public class into `internal`/`impl`;
    - pulling an outside package into a cycle is rejected.
  - The output format: `{"operations": [{"op": "moveClass", "class": "<fqn>", "to": "<pkg>"} | {"op": "invertEdge", "consumer": "<pkg>", "impl": "<fqn>"}], "rationale": "<one sentence>"}`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_agentic_context.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dsarp/agentic tests/test_agentic_context.py
git commit -m "Give the agentic planner a bounded view of one package cycle"
```

---

### Task 3: Planner agent with validation and architectural feedback

**Files:**
- Create: `dsarp/agentic/planner.py`, `tests/conftest.py` (the shared `Scripted` fake model)
- Test: `tests/test_agentic_planner.py`

**Interfaces:**
- Consumes: `build_context`, `render` (Task 2); `scc_planner.package_edges`, `scc_planner.components`; `accept(cls, dest) -> bool` from `scc_dissolve.move_accept`; `InversionFacts.blocked(consumer, impl, moved) -> Optional[str]` (may be `None`, which turns inversions off).
- Produces:
  - `parse_ops(text: str) -> Tuple[List[Op], List[str]]`: operations, plus parse errors.
  - `validate(ops: List[Op], edges, comp: Set[str], accept, blocked) -> Dict[str, Any]` with keys `ops` (kept), `rejected` (`[[op_label, reason]]`), `predicted_left`, `pulled_in`, `left_packages`.
  - `llm_plan(model, edges, comp: Set[str], accept, blocked, rounds: int = 3) -> Dict` returns the shared plan dict. On a model error it returns `moves=[]`, `predicted_left=size` and `why="model call failed: ..."`.

- [ ] **Step 1: Write the failing tests**

```python
EDGES = {("a.X", "b.Y"), ("b.Y", "a.Z")}          # a <-> b
OK = '{"operations":[{"op":"moveClass","class":"b.Y","to":"a"}],"rationale":"r"}'

def test_parse_takes_first_json_inside_fence():
    ops, errs = parse_ops("Sure!\n```json\n" + OK + "\n```")
    assert ops == [("move", "b.Y", "a")] and errs == []

def test_unknown_and_nested_names_rejected():
    v = validate([("move", "b.Y$Inner", "a"), ("move", "Y", "a")], EDGES, {"a", "b"}, lambda c, d: True, None)
    assert [r[1] for r in v["rejected"]] == ["unknown class", "unknown class"]

def test_feedback_then_dissolving_plan():
    bad = '{"operations":[{"op":"moveClass","class":"b.Nope","to":"a"}]}'
    m = Scripted(bad, OK)
    plan = llm_plan(m, EDGES, {"a", "b"}, lambda c, d: True, None, rounds=3)
    assert plan["moves"] == [["b.Y", "a"]] and plan["predicted_left"] == 0 and plan["dissolves"]
    assert "b.Nope: unknown class" in m.prompts[1] and len(plan["rounds"]) == 2

def test_plan_pulling_outside_package_into_cycle_is_rejected():
    edges = EDGES | {("c.Q", "a.X")}
    pull = '{"operations":[{"op":"moveClass","class":"a.X","to":"c"}]}'
    plan = llm_plan(Scripted(pull, pull, pull), edges, {"a", "b"}, lambda c, d: True, None, rounds=3)
    assert plan["moves"] == [] and plan["predicted_left"] == 2

def test_model_down_is_recorded_not_raised():
    class Down:
        def generate(self, *a, **k): raise RuntimeError("unreachable")
    plan = llm_plan(Down(), EDGES, {"a", "b"}, lambda c, d: True, None)
    assert plan["moves"] == [] and plan["why"].startswith("model call failed")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `py -m pytest tests/test_agentic_planner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dsarp.agentic.planner'`

- [ ] **Step 3: Implement in `dsarp/agentic/planner.py`**
  - **Known names.** Known classes are the top-level classes in `edges`; known packages are their packages.
  - **Rejection reasons**, using exactly these strings:
    - `unknown class`;
    - `unknown package`;
    - `class moved twice`;
    - `refused: move rule` (when `accept` is False);
    - the text returned by `blocked`.
  - **Simulation.** Kept operations are simulated with `package_edges(edges, moved, inverted)`. `pulled_in` counts packages cycling now that did not cycle at baseline.
  - **Planning loop.** `llm_plan` calls `model.generate(render(ctx, feedback), max_tokens=800, temperature=0.2, json_mode=True)`.
    - It stops early when there are no rejections, `pulled_in == 0` and `predicted_left == 0`.
    - Otherwise the feedback lists each rejection as `<op label>: <reason>`, plus `still cycling: <left_packages>`.
    - It returns the best round by `(pulled_in > 0, predicted_left, len(ops))`. A best round with `pulled_in > 0` yields no operations.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_agentic_planner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dsarp/agentic/planner.py tests/conftest.py tests/test_agentic_planner.py
git commit -m "Add the LLM planner, held to the catalogue and the simulated graph"
```

---

### Task 4: Freeze LLM plans on the beam arm's targets

**Files:**
- Create: `dsarp/agentic/run.py`
- Test: `tests/test_agentic_run.py`

**Interfaces:**
- Consumes:
  - `llm_plan` (Task 3);
  - `scc_dissolve.prepare`, `freeze`, `cannot_freeze`, `move_accept`, `arm_matches` (Task 1);
  - `mixed_plan.dry_run(repo, plan, work)`;
  - `InversionFacts(snapshot, facts).blocked`;
  - `LocalProvider(model, base_url, api_key=...)`.
- Produces:
  - `targets_from(path: Path) -> List[List[str]]`: the `component` lists of a beam preregistration.
  - `make_llm_plans(repo: Path, base: Dict, model, targets: List[List[str]], work: Path, rounds: int = 3) -> List[Dict]`: for each target, `llm_plan`; then a Spoon `dry_run`. A refused class is banned (accept returns False for it) and the planner reruns, at most `scc_dissolve.PLAN_ATTEMPTS` times. The output carries a `"refused"` list.
  - CLI: `py -m dsarp.agentic.run REPO OUT --targets-from PRE --model NAME --base-url URL --api-key-env VAR --freeze`.

- [ ] **Step 1: Write the failing tests**

```python
def test_targets_from_reads_components(tmp_path):
    p = tmp_path / "preregistration.json"
    p.write_text(json.dumps({"plans": [{"component": ["a", "b"]}, {"component": ["c", "d", "e"]}]}))
    assert targets_from(p) == [["a", "b"], ["c", "d", "e"]]

def test_spoon_refusal_bans_and_replans(monkeypatch, tmp_path):
    seen = []
    def fake_plan(model, edges, comp, accept, blocked, rounds=3):
        seen.append(accept("b.Y", "a"))
        return {"component": sorted(comp), "size": 2, "moves": [["b.Y", "a"]], "inversions": [],
                "predicted_left": 0, "dissolves": True, "planner": "llm", "rounds": []}
    verdicts = iter([{"ok": False, "refused": "b.Y", "why": "visibility"}, {"ok": True}])
    monkeypatch.setattr(run, "llm_plan", fake_plan)
    monkeypatch.setattr(run, "dry_run", lambda *a: next(verdicts))
    monkeypatch.setattr(run, "_accept_for", lambda repo, banned: (lambda c, d: c not in banned))
    plans = run.make_llm_plans(tmp_path, {"edges": [["a.X", "b.Y"], ["b.Y", "a.Z"]], "snapshot": {}},
                               object(), [["a", "b"]], tmp_path)
    assert seen == [True, False] and plans[0]["refused"] == ["b.Y"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `py -m pytest tests/test_agentic_run.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dsarp.agentic.run'`

- [ ] **Step 3: Implement `dsarp/agentic/run.py`**
  - Add the helper `_accept_for(repo: Path, banned: set) -> Callable` around `move_accept(SourceFacts(repo), banned)`.
  - `main` handles `--freeze` only in this task:
    1. `select_jdk`;
    2. `prepare`;
    3. load the baseline tests and refuse via `cannot_freeze`;
    4. `make_llm_plans`;
    5. `freeze(..., arm)` with the arm from Global Constraints.
  - Model failures stay inside the plan dict, so one bad target never stops the run.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_agentic_run.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dsarp/agentic/run.py tests/test_agentic_run.py
git commit -m "Freeze LLM plans on the beam arm's own targets"
```

---

### Task 5: Compiler and tester repair agent

**Files:**
- Create: `dsarp/agentic/repair.py`
- Test: `tests/test_agentic_repair.py`

**Interfaces:**
- Consumes: `gates.REFLECTIVE`.
- Produces:
  - `error_summary(log_text: str, limit: int = 20) -> List[str]`: Maven `[ERROR]` lines naming a `.java` file, deduplicated, in order.
  - `parse_edits(text: str) -> List[Dict[str, str]]`: edits in the form `{"path", "search", "replace"}`, from `{"edits": [...]}`.
  - `apply_edits(copy: Path, edits: List[Dict[str, str]], allowed: Set[str]) -> Dict[str, Any]` with keys `applied` (relative paths) and `refused` (`[[path, reason]]`).
  - `repair(model, copy: Path, allowed: Set[str], failure: str, rebuild: Callable[[], Dict[str, Any]], budget: int = 5) -> Dict[str, Any]` with keys `ok`, `rounds`, `edited`. `rebuild()` returns `{"ok": bool, "log": str}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_error_summary_keeps_java_errors_only():
    log = "[INFO] x\n[ERROR] /c/p/src/main/java/a/X.java:[3,8] cannot find symbol\n[ERROR] BUILD FAILURE\n"
    assert error_summary(log) == ["[ERROR] /c/p/src/main/java/a/X.java:[3,8] cannot find symbol"]

def test_edits_outside_scope_are_refused(tmp_path):
    for rel in ("src/main/java/a/X.java", "src/test/java/a/XTest.java", "pom.xml"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True); (tmp_path / rel).write_text("import b.Y;\n")
    allowed = {"src/main/java/a/X.java", "src/test/java/a/XTest.java", "pom.xml"}
    res = apply_edits(tmp_path, [{"path": p, "search": "import b.Y;", "replace": "import a.Y;"} for p in sorted(allowed)], allowed)
    assert res["applied"] == ["src/main/java/a/X.java"]
    assert sorted(r[1] for r in res["refused"]) == ["build file", "test source"]

def test_search_must_match_exactly_once(tmp_path):
    f = tmp_path / "X.java"; f.write_text("a; a;")
    res = apply_edits(tmp_path, [{"path": "X.java", "search": "a;", "replace": "b;"},
                                 {"path": "X.java", "search": "zz", "replace": "b"}], {"X.java"})
    assert [r[1] for r in res["refused"]] == ["search matched 2 times", "search matched 0 times"]

def test_reflective_workaround_refused(tmp_path):
    (tmp_path / "X.java").write_text("new Y();")
    res = apply_edits(tmp_path, [{"path": "X.java", "search": "new Y();",
                                  "replace": 'Class.forName("b.Y").newInstance();'}], {"X.java"})
    assert res["refused"] == [["X.java", "adds a reflective lookup"]]

def test_repair_stops_on_success_and_on_budget(tmp_path):
    (tmp_path / "X.java").write_text("bad")
    fix = '{"edits":[{"path":"X.java","search":"bad","replace":"good"}]}'
    ok = repair(Scripted(fix), tmp_path, {"X.java"}, "[ERROR] X.java bad",
                lambda: {"ok": (tmp_path / "X.java").read_text() == "good", "log": ""}, budget=5)
    assert ok["ok"] and len(ok["rounds"]) == 1 and ok["edited"] == ["X.java"]
    never = repair(Scripted(*["{}"] * 2), tmp_path, {"X.java"}, "e", lambda: {"ok": False, "log": "e"}, budget=2)
    assert not never["ok"] and len(never["rounds"]) == 2
```

- [ ] **Step 2: Run them to verify they fail**

Run: `py -m pytest tests/test_agentic_repair.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dsarp.agentic.repair'`

- [ ] **Step 3: Implement `dsarp/agentic/repair.py`**
  - **Refusal reasons are checked in this order**, using exactly these strings:
    1. `outside working copy`;
    2. `test source` (any `src/test/` segment);
    3. `build file` (`pom.xml`, `*.gradle`, any `META-INF/` segment);
    4. `not in scope`;
    5. `adds a reflective lookup` (the replacement contains a `gates.REFLECTIVE` token not present in the search text);
    6. `search matched N times`.

    Tests and build files are refused even when listed in `allowed`.
  - **Each round:**
    1. Prompt with the failure summary, the current text of each allowed file (capped at 400 lines per file), and the previous round's refusals.
    2. Call `model.generate(prompt, max_tokens=1500, temperature=0.2, json_mode=True)`.
    3. Apply the edits, then call `rebuild()`.
    4. Stop on `ok`, or once `budget` rounds have run.

    The next failure text is `"\n".join(error_summary(log))`, or the raw log tail when the summary is empty.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_agentic_repair.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dsarp/agentic/repair.py tests/test_agentic_repair.py
git commit -m "Add the scoped compiler and tester repair agent"
```

---

### Task 6: Run the loop through the gates

**Files:**
- Modify: `dsarp/experiments/scc_dissolve.py` (`measure`, the build step at lines 249-254 and the tests step at lines 278-287)
- Modify: `dsarp/agentic/run.py` (add `--confirm`, `--repair-budget`, `check_frozen`, `make_hook`)
- Test: `tests/test_scc_dissolve_apply.py` (extend), `tests/test_agentic_run.py` (extend)

**Interfaces:**
- Consumes: `repair` (Task 5), `_apply_plan` and `arm_matches` (Task 1), `measure`, `facade_first`, `summarise`, `compile_repo`, `run_tests`, `_changed_java`.
- Produces:
  - `measure(..., repair_hook: Optional[Callable[[Path, str, str], Dict[str, Any]]] = None)`, where the hook receives `(copy, stage, failure_text)` with `stage` either `"build"` or `"tests"`.
  - `_build_with_repair(copy: Path, work: Path, repair_hook) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]`.
  - `row["repair"] = {"build": <repair result or None>, "tests": <repair result or None>}`.
  - `run.check_frozen(out: Path, arm: Dict) -> Dict` (the preregistration).
  - `run.make_hook(model, scope: Set[str], budget: int) -> Callable`.

- [ ] **Step 1: Write the failing tests**

```python
def test_build_repair_hook_reruns_compile(monkeypatch, tmp_path):
    builds = iter([{"ok": False, "status": "compile_failed", "javac_errors": ["e"]}, {"ok": True, "status": "compiled"}])
    monkeypatch.setattr(sd, "compile_repo", lambda *a, **k: next(builds))
    hook = lambda copy, stage, text: {"ok": True, "rounds": [{}], "edited": ["X.java"], "stage": stage}
    build, rec = sd._build_with_repair(tmp_path, tmp_path, hook)
    assert build["ok"] and rec["stage"] == "build"

def test_no_hook_keeps_old_behaviour(monkeypatch, tmp_path):
    monkeypatch.setattr(sd, "compile_repo", lambda *a, **k: {"ok": False, "status": "compile_failed"})
    build, rec = sd._build_with_repair(tmp_path, tmp_path, None)
    assert not build["ok"] and rec is None

def test_confirm_refuses_other_arm(tmp_path):
    (tmp_path / "preregistration.json").write_text(json.dumps(
        {"arm": {"engine": "text", "facades": True, "operators": "moves", "repair": False}, "plans": []}))
    with pytest.raises(SystemExit, match="frozen for"):
        run.check_frozen(tmp_path, {"engine": "text", "facades": True, "operators": "mixed",
                                    "repair": False, "planner": "llm", "model": "m"})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `py -m pytest tests/test_scc_dissolve_apply.py tests/test_agentic_run.py -v`
Expected: FAIL with `AttributeError: ... '_build_with_repair'` and `... 'check_frozen'`

- [ ] **Step 3: Implement**
  - **`_build_with_repair`:** compiles. On failure with a hook, it calls `hook(copy, "build", "\n".join(build.get("javac_errors") or []))` and then compiles once more. The repair loop rebuilds inside itself, so this final compile is the record of truth.
  - **`measure`:**
    - Use `_build_with_repair` for the build step.
    - When `behavioural` reports `newly_failing` after flake settling and a hook exists, call the hook with stage `"tests"` and the failing test names. Then rerun `run_tests` and recompute `behavioural`.
    - The reflection gate already runs after tests, so it also covers repaired files.
    - The scope given to the hook is `{p for p in _changed_java(repo, copy) if "src/test/" not in p}`, as paths relative to the copy.
  - **`run.main --confirm`:**
    - `check_frozen(out, arm)` raises `SystemExit("frozen for ...")` through `arm_matches`.
    - `measure` runs through `facade_first` when `--facades` is set.
    - The hook is `make_hook(model, scope, budget)`, or `None` when `--repair-budget 0`.
    - Rows go to `rows.jsonl` when the budget is 0, and to `rows_repair.jsonl` otherwise. The summary is written beside them.

- [ ] **Step 4: Run all tests**

Run: `py -m pytest tests -q`
Expected: every test passes, including the earlier `test_gates.py`, `test_scc_planner.py`, `test_facades.py` and `test_arm_compare.py`

- [ ] **Step 5: Commit**

```bash
git add dsarp/experiments/scc_dissolve.py dsarp/agentic/run.py tests/test_scc_dissolve_apply.py tests/test_agentic_run.py
git commit -m "Run the agentic loop through the existing gates, with repair as a separate arm"
```

---

### Task 7: Model check, then the paired comparison

**Files:**
- Modify: `data/memory/current_status.md`, `data/memory/hourly_log.md`
- No new code. This task runs what Tasks 1-6 built.

**Interfaces:**
- Consumes: `py -m dsarp.agentic.run`, `arm_compare.compare`, and the frozen beam runs in `%TEMP%\hold\<repo>` and `%TEMP%\hold_ext\apache-mina-sshd`.

- [ ] **Step 1: Model check on three known targets**

Freeze LLM plans for Commons Exec, Commons Math and Commons Text (targets from their beam preregistrations) into `%TEMP%\agentic_smoke\<repo>`. Pass bar: at least 2 of the 3 plans are `dissolves: true` after the Spoon dry run. If the bar fails, stop and report the model's rounds. The spec's warning applies: `qwen2.5-coder:3b` scored 0 of 6.

```bash
py -m dsarp.agentic.run %TEMP%\hold\apache-commons-exec\baseline_tree %TEMP%\agentic_smoke\apache-commons-exec --targets-from %TEMP%\hold\apache-commons-exec\preregistration.json --model <name> --base-url <url> --api-key-env DSARP_LLM_KEY --freeze
```

Expected: `frozen: ...preregistration.json`, with each plan's `rounds` recorded.

- [ ] **Step 2: Freeze the agentic arm on the 10 Holdout repos and mina-sshd that froze targets**

The same command with `OUT=%TEMP%\agentic\<repo>`. These are the beam arm's 33 targets: 29 Holdout plus 4 from mina-sshd.

- [ ] **Step 3: Confirm without repair, then with repair**

```bash
py -m dsarp.agentic.run <baseline_tree> %TEMP%\agentic\<repo> --targets-from <beam pre> --model <name> --base-url <url> --api-key-env DSARP_LLM_KEY --confirm --engine text --facades --repair-budget 0
py -m dsarp.agentic.run <baseline_tree> %TEMP%\agentic\<repo> --targets-from <beam pre> --model <name> --base-url <url> --api-key-env DSARP_LLM_KEY --confirm --engine text --facades --repair-budget 5
```

Expected: `rows.jsonl` and `rows_repair.jsonl` per repo, each followed by a summary JSON.

- [ ] **Step 4: Paired comparison**

Feed `arm_compare.compare` with `{"beam": <hold rows>, "llm": <agentic rows.jsonl>, "llm+repair": <agentic rows_repair.jsonl>}`. Report for each arm:
- the 4c-accepted rate with its Wilson interval;
- exact McNemar between each pair;
- API breaks for each 4c row;
- repair rounds used;
- model token counts from `Completion.prompt_tokens` and `completion_tokens`.

Then rerun Arcan on accepted rows and count the packages Arcan names in cycles. This is the stable measure from the 2026-11-06 recount, not the cycle count.

- [ ] **Step 5: Record and commit**

Add an AGENTIC ARM section to `current_status.md` with the numbers above, labelled confirmatory for the frozen arms. Add an hourly-log row.

```bash
git add data/memory/current_status.md data/memory/hourly_log.md
git commit -m "Record the agentic arm against the beam arm on the frozen targets"
```

---

## How RefAgent itself refactors, and where this plan departs

Source: Oueslati, Lamothe, Khomh, arXiv 2511.03153v2, sections 3 to 7, read 2026-11-15.

| Step | RefAgent (paper) | This plan |
|---|---|---|
| Unit of work | One class at a time, picked at random, with its first-degree jdeps dependencies (§3.1, §3.2) | One package cycle, taken from the beam arm's frozen targets |
| Planner input | jdeps class graph, DesigniteJava metrics only; smell detection is not used, to avoid bias (§3.2) | Package edges, the class edges that carry them, and the rules the validator enforces |
| Plan | Code regions (method, field, variable) with refactoring instructions in prose | JSON operations from a two-entry catalogue: `moveClass`, `invertEdge` |
| Check before writing | None | Names checked against the graph, effect simulated, Spoon dry run |
| Generator | An LLM returns the improved class as Java source (§3.3) | Deterministic engines (text engine, Spoon); the LLM writes no new code |
| Compiler agent | Maven compile; an LLM summarises the log with fix instructions and sends it back to the generator; up to 20 rounds (§3.4) | Maven test-compile; the LLM proposes search/replace edits limited to files the plan touched; up to 5 rounds |
| Tester agent | Developer tests found via jdeps plus EvoSuite tests generated on the original class; failures go back to the generator; up to 20 rounds; a class that still fails is left unchanged (§3.5) | The project's own full suite, flake reruns, repair under the same scope rules; EvoSuite deferred |
| Acceptance | Compiles and tests pass (§7) | The existing gates: structure (ArchUnit), reflection, services, tests; Arcan and japicmp reported |
| Refactorings | 23 types found by RefactoringMiner 3.0, mostly inside classes: Extract Method, Invert Condition, Rename Attribute and others (§5.1.3) | Architectural only: move class between packages, invert an edge through an interface |
| Reported results | 8 Apache projects; median 90% unit-test pass, 87-88% compile, 52.5% smell reduction with GPT-4o (Table 3); pass rates level off after about 12 rounds (§5.3.5) | Measured against the beam arm and the teammate pipeline on the same Tika commit |
| Stated limits | Class level only; no claim about package or architectural refactoring (§7, §8) | Package cycles only; class-internal refactorings need a Spoon operator first |

Consequence for the comparison: RefAgent's headline numbers come from class-level refactorings judged by compile and tests. They are a reference point, not a like-for-like result. Only the Tika runs here use the same commit, the same gates and the same Arcan count.

## Not in this plan

- **EvoSuite regression tests:** RefAgent's tester generates them; this plan uses the projects' own suites with flake reruns. Add them when a repaired change passes the project tests but a reviewer finds a behaviour change.
- **Move Method and other class-internal operations:** they need a Spoon operator first.
- **LLM-written source for operations with no engine:** the generator stays deterministic, so the planner cannot invent code.
- **Raising the repair budget towards RefAgent's 20:** only if `rows_repair.jsonl` shows successes in rounds 4-5.
