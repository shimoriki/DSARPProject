"""Spoon refactoring agent — evidence in, executable moves out, detector verdict on top.

Two sources can drive it:

  arcan_findings()      the detector's own findings, one at a time. Each carries an
                        evidence_id, so every edit traces back to a specific measurement.
  transformer_plans     the separately-trained model's predictions, read from CSV.

The Arcan path is the default now. On log4j2 the transformer contributes no usable signal —
716 rows, top-1 label constant across all of them, every confidence inside 0.511-0.521, and
`Move Class` (the one executable op) never ranked first. What it does supply, affected
packages and severity, is Arcan's own output restated, so reading Arcan directly is both
shorter and better evidenced.

RefactoringMiner history supplies few-shot exemplars: package moves developers actually made
and shipped. They show the SHAPE of a real move, and are never instructions about this repo.

The model is the only unverified link in the chain, and it is bracketed on both sides — an
op allowlist and a source check before, a compile and a real detector after. A plan that
reads beautifully and does not move the smell count is recorded as a failure.

Verification is BATCHED: one baseline measurement, every surviving edit applied to one copy,
one re-measurement. Per-edit attribution would be better evidence, but Arcan on log4j2 costs
minutes per run and 50 trials would not finish.
# ponytail: batched verification, go per-edit if attribution matters more than wall clock
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..refactoring import exemplars as exemplar_store
from ..refactoring import spoon_plan
from ..refactoring.strategies import SourceFacts

PROMPT = """SMELL: {smell}   [evidence {evidence_id}, severity {severity}]
AFFECTED COMPONENTS: {components}
DETECTOR METRICS: {metrics}

DEPENDENCY GRAPH AROUND THIS SMELL (fan_in/fan_out per package, then the edges):
{graph}

CANDIDATE MOVES — every one of these has already been checked against the source and is
legal to apply. Choose from them by NUMBER. Do not write class or package names.
{candidates}

MOVES DEVELOPERS ACTUALLY MADE IN THESE PROJECTS (shape reference, not instructions):
{examples}

Reply with exactly this JSON:
  {{"pick": [<numbers, at most 3>], "reasoning": "<one sentence>"}}
Pick the move that best breaks THIS smell. `"pick": []` is correct when none of them would.
"""


def build_graph(project_id: str, repo_path: Path):
    """The package dependency graph, built exactly as graph_agent builds it.

    Reused rather than re-derived: SourceIndexer already extracts the import edges and
    DependencyGraphBuilder already turns them into the networkx graph the rest of DSARP
    reasons over.
    """
    from ..graphs.builder import DependencyGraphBuilder
    from ..source_index.indexer import SourceIndexer
    idx = SourceIndexer().index(project_id, repo_path)
    return DependencyGraphBuilder().build(idx.import_edges)


def arcan_findings(data_dir: Path, project_id: str, repo_path: Optional[Path] = None,
                   out_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Detector findings straight from the normalised Arcan output.

    Shaped like the transformer plans so both sources feed one agent: smell_type,
    components, severity, plus the evidence_id that makes an edit citable.

    Only seven repositories have a precomputed file. An UNSEEN repository has none, and
    returning [] there quietly reduced the agent to "works on the repos we already analysed"
    — so when `repo_path` is given the detector is run live instead. Live findings carry no
    evidence_id, which is exactly right: there is no stored evidence to cite yet.
    """
    path = Path(data_dir) / "raw" / "arcan" / f"{project_id}.json"
    stored = []
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stored = []
    # A file that exists but holds almost nothing is worse than no file: apache-tika.json
    # carries ONE finding while the same commit's predictions list 261 cyclic dependencies.
    # Treating "present" as "usable" silently reduced the run to that single finding, so a
    # stale file now falls through to live detection the same way a missing one does.
    if len(stored) < 2:
        if repo_path is None:
            return _normalise_stored(stored)
        from ..verification.openrewrite_loop import detect
        res = detect(Path(repo_path), Path(out_dir or Path(data_dir) / "outputs" /
                                           f"{project_id}__detect"), "arcan")
        return [{"smell_type": f.get("smell_type"),
                 "components": list(f.get("components") or []),
                 "severity": f.get("severity"), "metrics": {},
                 "evidence_id": None, "source": "arcan-live"}
                for f in (res.get("findings") or [])]
    return _normalise_stored(stored)


def _normalise_stored(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Precomputed Arcan findings, shaped like every other source the agent accepts."""
    return [{"smell_type": f.get("smell_type"),
             "components": list(f.get("affected_components") or []),
             "severity": f.get("severity"),
             "metrics": f.get("metrics") or {},
             "evidence_id": f.get("evidence_id"),
             "source": "arcan"}
            for f in raw]


def _atdi(finding: Dict[str, Any]) -> float:
    """Arcan's architectural debt index — the detector's own severity ordering."""
    try:
        return float((finding.get("metrics") or {}).get("ATDI") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def graph_neighbours(graph, pkg: str) -> List[str]:
    """Packages this one depends on, or that depend on it.

    A 1-hop slice_around is exactly this question, and it goes through networkx instead of
    scanning every edge per call.
    """
    if graph is None:
        return []
    from ..graphs.builder import DependencyGraphBuilder
    sl = DependencyGraphBuilder.slice_around(graph, [pkg], hops=1)
    return [n["id"] for n in sl.get("nodes", []) if n["id"] != pkg]


def candidate_targets(facts: SourceFacts, components: List[str],
                      limit: int = 12, graph=None) -> List[str]:
    """Packages a type in this finding may legally be moved to.

    Only Cyclic Dependency names more than one package. Hub-like Dependency, God Component
    and Unstable Dependency each name exactly ONE, and offering that single package back as
    a target asks the model to move a class into the package it already lives in — which
    validate() then rejects as "source and target package are the same".

    So for a single-package finding the targets are, in order of preference:
      1. the package's existing siblings, same Maven module;
      2. failing that, its GRAPH neighbours, same module — the packages it actually trades
         dependencies with, which for a hub is exactly where its load should go.
    Naming alone is a weak proxy for where a type belongs; the graph is the real relation,
    and it reaches findings that have no sibling packages at all.
    """
    known = [c for c in components if c in set(facts.packages())]
    if len(known) >= 2:
        return known
    if not known:
        return []
    pkg = known[0]
    # Same Maven module only. A target in another module is one validate() rejects every
    # time, so offering it just buys a wasted call and a rejection.
    home = spoon_plan.package_root(facts, pkg)

    def same_module(p: str) -> bool:
        return p != pkg and spoon_plan.package_root(facts, p) == home

    parent = pkg.rsplit(".", 1)[0]
    siblings = sorted(p for p in facts.packages()
                      if p.rsplit(".", 1)[0] == parent and same_module(p))
    if siblings:
        return siblings[:limit]
    known_pkgs = set(facts.packages())
    return [p for p in graph_neighbours(graph, pkg)
            if p in known_pkgs and same_module(p)][:limit]


def graph_block(graph, components: List[str], targets: List[str],
                max_edges: int = 15) -> str:
    """A compact slice of the dependency graph around this smell.

    Never the whole graph — the token policy exists because a 167-package dump would bury
    the three edges that matter. Fan-in/fan-out is included because it is what makes a hub
    legible as a hub.
    """
    if graph is None:
        return "  (graph not built for this run)"
    from ..graphs.builder import DependencyGraphBuilder
    focus = [c for c in list(components) + list(targets) if c]
    sl = DependencyGraphBuilder.slice_around(graph, focus, hops=1)
    if not sl.get("nodes"):
        return "  (affected packages are not in the graph)"
    interesting = set(focus)
    # A hub's slice lists 40+ packages. Keep the heaviest ones: fan-in/fan-out is only
    # useful for spotting where the weight sits, and listing every node buries that in a
    # 4096-token window.
    nodes = [n for n in sl["nodes"] if n["id"] in interesting]
    nodes.sort(key=lambda n: -(int((n.get("metrics") or {}).get("fan_in", 0) or 0)
                               + int((n.get("metrics") or {}).get("fan_out", 0) or 0)))
    lines = []
    for n in nodes[:10]:
        m = n.get("metrics") or {}
        lines.append(f"  {n['id']}  fan_in={m.get('fan_in', '?')} "
                     f"fan_out={m.get('fan_out', '?')}")
    if len(nodes) > 10:
        lines.append(f"  … and {len(nodes) - 10} lighter packages")
    edges = [e for e in sl["edges"]
             if e["source"] in interesting and e["target"] in interesting]
    lines.append(f"  edges ({len(edges)} of {sl['edge_count']} in the slice):")
    lines += [f"    {e['source']} -> {e['target']}" for e in edges[:max_edges]]
    return "\n".join(lines)


def named_type_candidates(facts: SourceFacts, components: List[str]) -> List[tuple]:
    """Moves derivable from components that name a CLASS rather than a package.

    463 of log4j2's 584 Arcan `affected_components` are class names — `org.apache.log4j.
    Appender`, `com.example.ExampleConfiguration`. The pipeline filtered them out against
    facts.packages() and threw away the most actionable finding shape there is: the detector
    naming the exact class. Here the class is the type to move, and the target is another
    affected component's package that it actually references.
    """
    known_pkgs = set(facts.packages())
    types = [c for c in components
             if c not in known_pkgs and facts.file_for(c) and not facts.is_nested(c)]
    if not types:
        return []
    targets = {c for c in components if c in known_pkgs}
    targets |= {c.rsplit(".", 1)[0] for c in types if c.rsplit(".", 1)[0] in known_pkgs}
    out = []
    for fqn in types:
        home = fqn.rsplit(".", 1)[0]
        src_root = spoon_plan.source_root_of(facts, fqn)
        text = facts.text_of(fqn)
        for t in sorted(targets):
            if t == home or spoon_plan.package_root(facts, t) != src_root:
                continue
            if t in text:                     # the class really does reach into that package
                out.append((fqn, t))
                break
    return out


def _crossing_summary(facts: SourceFacts, packages: List[str], limit: int = 12) -> str:
    """The concrete CLASSES that reference across the packages — the only legal `type`s.

    nemotron-mini put a PACKAGE name in the `type` field on 12 of the first 15 findings,
    because the prompt is almost entirely package names and this was the one section
    carrying class names, written as prose. Stating it as an explicit pick-from list, with
    the owning package on its own line so it cannot be mistaken for part of the name, is
    what makes the class/package distinction survive a 4B model.
    """
    lines: List[str] = []
    seen = set()
    root_of = {p: spoon_plan.package_root(facts, p) for p in packages}
    for a in packages:
        for b in packages:
            if a == b:
                continue
            # Never offer a move the validator will refuse. On log4j2 most cycles span
            # Maven modules (api <-> core), and those moves need a new module dependency to
            # compile — so listing them only produces confident, rejected plans.
            if root_of.get(a) is None or root_of.get(a) != root_of.get(b):
                continue
            for fqn in facts.crossing_classes(a, b)[:4]:
                if fqn in seen:
                    continue
                seen.add(fqn)
                # Each line is a COMPLETE legal edit: crossing_classes(a, b) means this
                # class sits in a and reaches into b, so b is where it belongs. Spelling the
                # target out per entry removes the last decision the model kept getting
                # wrong — it was picking toPackage = the package the class is already in.
                lines.append(f"  {fqn}\n"
                             f"      type: {fqn}\n"
                             f"      toPackage: {b}")
            if len(lines) >= limit:
                return "\n".join(lines[:limit])
    return "\n".join(lines) or "  (none — decline, there is no class to move)"


def candidate_edits(facts: SourceFacts, finding: Dict[str, Any], graph=None,
                    limit: int = 12) -> List[spoon_plan.Edit]:
    """Every legal move this finding admits, enumerated from the source.

    This is the point of the redesign. Asking a model to AUTHOR `{type, toPackage}` put it
    in the business of naming things, and it failed in the three ways a language model
    always fails at naming: it wrote a package where a class belonged, it targeted the
    package the class was already in, and it proposed moves across build modules. All three
    are decidable from the source, so they are decided here, and the model is left with the
    one question it is actually good at — which of these is worth doing.

    A candidate that survives _why_not() is applicable by construction, so the model can no
    longer produce an INAPPLICABLE plan. It can still produce an unhelpful one, and the
    Arcan gate already judges that.
    """
    comps = [c.strip() for c in (finding.get("components") or []) if c.strip()]
    known = [c for c in comps if c in set(facts.packages())]
    targets = candidate_targets(facts, comps, graph=graph)
    scope = (known + targets) if len(known) < 2 else known

    legal: List[spoon_plan.Edit] = []
    seen = set()
    root_of = {p: spoon_plan.package_root(facts, p) for p in scope}

    def take(fqn: str, target: str) -> bool:
        """Validate one candidate; True once `limit` is reached."""
        if fqn in seen:
            return False
        seen.add(fqn)
        e = spoon_plan.Edit("moveClass", fqn, target)
        if not spoon_plan._why_not(e, facts):
            legal.append(e)
        return len(legal) >= limit

    # Enumerate and validate in one pass, stopping at `limit`. crossing_classes() unions the
    # mention-index for every class of the target package, so a 12-package scope is 132 of
    # those — building them all up front and validating afterwards made this the slowest
    # thing in the pipeline by a wide margin.
    for a in scope:
        for b in scope:
            if a == b or root_of.get(a) is None or root_of.get(a) != root_of.get(b):
                continue
            for fqn in facts.crossing_classes(a, b)[:4]:
                if take(fqn, b):
                    return legal
    for fqn, target in named_type_candidates(facts, comps):
        if take(fqn, target):
            break

    # Shuffle, seeded by the finding, so enumeration order does not privilege any candidate.
    # Measured on 12 findings: nemotron-mini picked candidate 1 twelve times out of twelve,
    # qwen2.5-coder:3b eleven, qwen2.5-coder:7b ten. Under an unshuffled list that reads as
    # "the models agree with my ordering"; it is indistinguishable from position bias. With
    # the order decorrelated, picking position 1 every time IS the null result, and a model
    # that tracks the same underlying move across orderings is genuinely selecting.
    random.Random(str(finding.get("evidence_id") or comps)).shuffle(legal)
    return legal


def prompt_for(finding: Dict[str, Any], facts: SourceFacts, examples: str = "  (none)",
               graph=None, candidates: Optional[List[spoon_plan.Edit]] = None) -> str:
    comps = [c.strip() for c in (finding.get("components") or []) if c.strip()]
    known = [c for c in comps if c in set(facts.packages())]
    if candidates is None:
        candidates = candidate_edits(facts, finding, graph)
    lines = [f"  {i}. move class {e.type}\n"
             f"       out of {e.type.rsplit('.', 1)[0]}\n"
             f"       into   {e.to_package}"
             for i, e in enumerate(candidates, 1)] or ["  (none — reply with an empty pick)"]
    metrics = finding.get("metrics") or {}
    # A hub can name 30+ packages. The full list is context, not instruction — it pushed the
    # median prompt past 2500 tokens on a model with a 4096 window, crowding out the
    # candidate list, which is the part that has to be read carefully.
    shown = ", ".join(comps[:8]) + (f", … (+{len(comps) - 8} more)" if len(comps) > 8 else "")
    return PROMPT.format(
        smell=finding.get("smell_type", "?"),
        evidence_id=finding.get("evidence_id", "unknown"),
        severity=finding.get("severity", "?"),
        components=shown or "(none)",
        metrics=", ".join(f"{k}={v}" for k, v in list(metrics.items())[:6]) or "(none)",
        graph=graph_block(graph, known, candidate_targets(facts, comps, graph=graph)),
        candidates="\n".join(lines),
        examples=examples)


def parse_picks(raw: str, candidates: List[spoon_plan.Edit], smell_type: str = "",
                component: str = "") -> spoon_plan.Plan:
    """Map the model's chosen numbers back to enumerated edits.

    An out-of-range number is recorded as a rejection rather than dropped: it is the one
    remaining way the model can be wrong here, so it should be visible in the ledger.
    """
    p = spoon_plan.Plan(smell_type=smell_type, component=component, raw=raw or "")
    # Reasoning models (qwen3, deepseek-r1) emit a <think> block first. It often contains
    # braces, so searching the raw text finds the model's scratch work instead of its answer
    # — and an unclosed block means the JSON never arrives inside the token budget at all.
    body = re.sub(r"<think>.*?</think>", "", p.raw, flags=re.S)
    body = re.sub(r"^.*?</think>", "", body, flags=re.S) if "</think>" in body else body
    m = re.search(r"\{.*\}", body, re.S)
    if not m:
        p.rejection = "model did not return JSON"
        return p
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        p.rejection = f"model returned invalid JSON: {e}"
        return p
    p.reasoning = str(data.get("reasoning", ""))[:200]
    picks = data.get("pick")
    if picks is None:
        p.rejection = "model returned JSON without a 'pick' list"
        return p
    for n in list(picks)[:3]:
        try:
            i = int(n)
        except (TypeError, ValueError):
            p.rejected.append({"edit": str(n)[:60], "why": "pick is not a number"})
            continue
        if 1 <= i <= len(candidates):
            p.edits.append(candidates[i - 1])
        else:
            p.rejected.append({"edit": str(n)[:60],
                               "why": f"pick {i} is outside 1..{len(candidates)}"})
    if not p.edits and not p.rejection:
        p.rejection = "no valid pick" if p.rejected else "model picked nothing"
    return p


def propose(model, finding: Dict[str, Any], facts: SourceFacts,
            examples: str = "  (none)", graph=None,
            candidates: Optional[List[spoon_plan.Edit]] = None) -> spoon_plan.Plan:
    """Enumerate the legal moves, then ask the model to choose among them.

    Never raises: an unreachable model is a rejected plan, not a crashed run.
    """
    comps = finding.get("components") or []
    smell, comp = finding.get("smell_type", ""), (comps[0] if comps else "")
    if candidates is None:
        candidates = candidate_edits(facts, finding, graph)
    if not candidates:
        p = spoon_plan.Plan(smell_type=smell, component=comp)
        p.rejection = "no legal move exists for this finding"
        return p
    try:
        raw = model.generate(prompt_for(finding, facts, examples, graph, candidates),
                             max_tokens=300, temperature=0.1, json_mode=True).text or ""
    except Exception as e:
        p = spoon_plan.Plan(smell_type=smell, component=comp)
        p.rejection = f"model call failed: {e}"
        return p
    return parse_picks(raw, candidates, smell, comp)


def run_trials(cfg, project_id: str, repo_path: Path, findings: List[Dict[str, Any]],
               model, out_dir: Path, detector: str = "arcan", budget: int = 8,
               examples: str = "  (none)", graph=None,
               before: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Propose, apply once, and cross-check with the detector. Returns the whole record."""
    from ..tools.spoon_runner import apply_edits, build_driver, driver_built
    from ..verification.effect_checker import _copy_repo
    from ..verification.openrewrite_loop import detect

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    record: Dict[str, Any] = {"project": project_id, "detector": detector, "plans": []}

    if not driver_built():
        built = build_driver()
        record["driver_build"] = built
        if not built.get("ok"):
            record["verdict"] = "driver_not_built"
            return record

    facts = SourceFacts(repo_path)
    # A finding with no legal target cannot produce an edit no matter what the model says,
    # so it is dropped before it costs a call. This also removes the highest-ATDI finding on
    # log4j2 — generated JMH benchmark code, 630 types, no sibling package to move anything
    # into — which severity ordering alone would otherwise put first.
    answerable = [f for f in findings
                  if candidate_targets(facts, f.get("components") or [], graph=graph)]
    record["findings_seen"] = len(findings)
    record["findings_answerable"] = len(answerable)
    edits: List[Dict[str, str]] = []
    for finding in answerable[:budget]:
        plan = propose(model, finding, facts, examples, graph)
        record["plans"].append({**plan.as_dict(),
                                "evidence_id": finding.get("evidence_id"),
                                "source": finding.get("source")})
        for e in plan.edits:
            d = e.as_dict()
            if d not in edits:
                edits.append(d)
        print(f"[{len(record['plans'])}/{min(budget, len(findings))}] "
              f"{finding.get('smell_type')}: {len(plan.edits)} edit(s)"
              f"{' | ' + plan.rejection if plan.rejection else ''}", flush=True)
    record["edits"] = edits
    if not edits:
        record["verdict"] = "no_applicable_edit"
        _save(out_dir, record)
        return record

    # Hand the machine back before the build starts. Everything below is Maven, Spoon and
    # Arcan — all JVMs — and a model left resident is several GB they will not get.
    if hasattr(model, "unload"):
        record["model_unloaded"] = model.unload()

    copy = _copy_repo(Path(repo_path), out_dir / "copy")
    if before is None:
        before = detect(copy, out_dir / "before", detector)
    else:
        # Every model in a sweep refactors the same commit, so the baseline is the same
        # measurement. Recomputing it per model would spend a compile + detector run each
        # time to learn a number we already have.
        record["baseline_reused"] = True
    record["before"] = {"smells": before.get("smells"), "by_type": before.get("by_type")}
    if not before.get("measured", before.get("ok")):
        record["verdict"] = "baseline_not_measured"
        _save(out_dir, record)
        return record

    facts_copy = SourceFacts(copy)
    plan_obj = spoon_plan.Plan(edits=[spoon_plan.Edit(op=e["op"], type=e["type"],
                                                     to_package=e["toPackage"])
                                      for e in edits])
    roots = [str(Path(r).relative_to(copy))
             for r in spoon_plan.source_roots_for(plan_obj, facts_copy)]
    applied = apply_edits(copy, edits, source_roots=roots, log_path=out_dir / "spoon.log")
    record["spoon"] = {k: applied.get(k) for k in ("ok", "status", "applied", "skipped")}
    if not applied.get("applied"):
        record["verdict"] = "spoon_applied_nothing"
        _save(out_dir, record)
        return record

    after = detect(copy, out_dir / "after", detector)
    ac = after.get("compile") or {}
    # Keep the whole compile record, not just its status. Storing the status string alone
    # meant a run that "compiled" by excluding the refactored module could not be re-judged
    # afterwards — the evidence that would have caught it was thrown away at write time.
    record["after"] = {"smells": after.get("smells"), "by_type": after.get("by_type"),
                       "compile": ac.get("status"),
                       "excluded_modules": ac.get("excluded_modules"),
                       "javac_errors": ac.get("javac_errors"),
                       "class_dirs": len(ac.get("class_dirs") or [])}
    record["before_compile"] = {
        "excluded_modules": (before.get("compile") or {}).get("excluded_modules"),
        "class_dirs": len((before.get("compile") or {}).get("class_dirs") or [])}
    record["verdict"] = verdict({**before, "compile": before.get("compile") or {}},
                               {**after, "compile": ac})
    record["deltas"] = smell_deltas(before, after,
                                    targeted=sorted({f.get("smell_type") for f in answerable[:budget]
                                                     if f.get("smell_type")}))
    _save(out_dir, record)
    return record


def _save(out_dir: Path, record: Dict[str, Any]) -> None:
    (out_dir / "spoon_trials.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


def smell_deltas(before: Dict[str, Any], after: Dict[str, Any],
                 targeted: Optional[List[str]] = None) -> Dict[str, Any]:
    """Change in the smell types the candidates aimed at, separately from everything else.

    A total that falls while the targeted type is unchanged is not a fix; a total that holds
    while the targeted type falls and something else rises is a trade the reviewer should
    see. Reporting one number hides both.
    """
    b, a = before.get("by_type") or {}, after.get("by_type") or {}
    keys = set(b) | set(a)
    tgt = set(targeted or [])
    per = {k: (a.get(k, 0) - b.get(k, 0)) for k in sorted(keys) if a.get(k, 0) != b.get(k, 0)}
    return {
        "targeted": {k: v for k, v in per.items() if k in tgt},
        "collateral": {k: v for k, v in per.items() if k not in tgt},
        "targeted_delta": sum(v for k, v in per.items() if k in tgt),
        "collateral_delta": sum(v for k, v in per.items() if k not in tgt),
    }


def verdict(before: Dict[str, Any], after: Dict[str, Any]) -> str:
    """Compile is checked first: a refactoring that does not build has not reduced anything,
    whatever a detector reports about the wreckage.

    But not every failed build is the refactoring's fault. A build that dies resolving
    dependencies, or on a JVM that never started, says nothing about the edits — reporting
    that as `rejected_build_broken` blames the change for the environment, which is how a
    whole model sweep came back looking like seven models writing broken code.
    """
    status = (after.get("compile") or {}).get("status")
    if status in ("dependency_unresolved", "jvm_start_failed", "compile_timeout",
                  "quality_gate_failed"):
        return f"inconclusive_{status}"
    if status != "compiled":
        return "rejected_build_broken"

    # "compiled" is not enough: compile_repo drops modules it cannot build and reports
    # success on the rest. On log4j2 that meant excluding log4j-core — the module that
    # received six of seven moves — and calling the result compiled with 36 class dirs
    # against a 37-dir baseline. A module the refactoring broke is a broken refactoring,
    # and comparing smell counts over different module sets measures nothing.
    dropped = set((after.get("compile") or {}).get("excluded_modules") or [])
    dropped -= set((before.get("compile") or {}).get("excluded_modules") or [])
    if dropped:
        return f"rejected_module_excluded:{','.join(sorted(dropped))}"
    if not after.get("measured", after.get("ok")):
        return "rejected_not_measured"
    b, a = before.get("smells"), after.get("smells")
    if b is None or a is None:
        return "rejected_not_measured"
    if a < b:
        return "kept_smells_reduced"
    return "rejected_no_reduction" if a == b else "rejected_smells_increased"


def spoon_refactor_agent(bb: Dict[str, Any]) -> Dict[str, Any]:
    """Blackboard entry point. Opt-in: it costs model calls and two detector runs.

    Findings come from the detector by default. `spoon_source="transformer"` uses the
    prediction CSV instead, which is kept so the two can be compared on the same gate.
    """
    if not bb.get("use_spoon"):
        return bb
    from ..models import get_provider

    data_dir = Path(bb["cfg"].data_dir)
    if bb.get("spoon_source") == "transformer":
        findings = bb.get("transformer_plans") or []
    else:
        findings = sorted(arcan_findings(data_dir, bb["project_id"]), key=_atdi, reverse=True)
        findings = findings or (bb.get("findings") or [])

    moves = exemplar_store.load(data_dir / "raw" / "refactoringminer")
    graph = bb.get("graph") or build_graph(bb["project_id"], Path(bb["repo_path"]))
    out = data_dir / "outputs" / f"{bb['project_id']}__spoon"
    model = get_provider(bb.get("model") or bb["cfg"].model_provider)
    # The skill the agent is documented by is the same text it is prompted with, so the
    # rules it is asked to follow cannot drift from the rules validate() enforces.
    if bb.get("skill_as_system_prompt", True) and hasattr(model, "system"):
        model.system = spoon_plan.system_prompt()
    bb["spoon_trials"] = run_trials(
        bb["cfg"], bb["project_id"], Path(bb["repo_path"]), findings, model, out,
        detector=bb.get("detector", "arcan"), budget=bb.get("spoon_budget", 8),
        examples=exemplar_store.as_prompt_block(moves), graph=graph)
    return bb


def implementations_used_by(facts: SourceFacts, consumer_pkg: str, impl_pkg: str,
                            limit: int = 4) -> List[str]:
    """Classes in `impl_pkg` that `consumer_pkg` actually names.

    The mirror of `crossing_classes`, which returns the classes that CREATE an edge. Cutting
    the edge by inversion needs the other end: the types on the far side that the consumer
    depends on, since those are the ones an abstraction can stand in front of.
    """
    consumer_files = {facts.file_for(f) for f in facts.classes_in(consumer_pkg)}
    consumer_files.discard(None)
    if not consumer_files:
        return []
    out = []
    for fqn in facts.classes_in(impl_pkg):
        if facts.files_mentioning(fqn.rsplit(".", 1)[-1]) & consumer_files:
            out.append(fqn)
            if len(out) >= limit:
                break
    return out


def dip_candidates(facts: SourceFacts, finding: Dict[str, Any], graph=None,
                   limit: int = 12) -> List[spoon_plan.Edit]:
    """Extract-Interface candidates for a cyclic-dependency finding.

    Kept separate from `candidate_edits` so the measured moveClass path is untouched and the
    two operations can be compared on the same findings rather than blended into one number.

    For every ordered pair of packages in the smell, the consumer is the package that names
    the other, and each class it names on the far side is one candidate. Dependency Inversion
    puts the interface in the CONSUMER's package, so `to_package` is the consumer here -- the
    opposite of what it means for a move, where it is the destination.
    """
    comps = [c.strip() for c in (finding.get("components") or []) if c.strip()]
    scope = [c for c in comps if c in set(facts.packages())]
    if len(scope) < 2:
        scope = (scope + candidate_targets(facts, comps, graph=graph))[:8]
    root_of = {p: spoon_plan.package_root(facts, p) for p in scope}

    out, seen = [], set()
    for consumer in scope:
        for impl_pkg in scope:
            if consumer == impl_pkg:
                continue
            # The interface lands in the consumer's module and the implements clause is
            # compiled in the other one; across modules that needs a build dependency that
            # very likely runs the wrong way.
            if root_of.get(consumer) is None or root_of.get(consumer) != root_of.get(impl_pkg):
                continue
            for fqn in implementations_used_by(facts, consumer, impl_pkg):
                key = (fqn, consumer)
                if key in seen:
                    continue
                seen.add(key)
                e = spoon_plan.Edit("extractInterface", fqn, consumer,
                                    interface_name=fqn.rsplit(".", 1)[-1] + "Api")
                if not spoon_plan._why_not(e, facts):
                    out.append(e)
                    if len(out) >= limit:
                        return out
    return out


def invert_edge_candidates(facts: SourceFacts, finding: Dict[str, Any], graph=None,
                           limit: int = 12, max_classes: int = 25) -> List[spoon_plan.Edit]:
    """One candidate per package EDGE: abstract every class the consumer names on the far side.

    Extracting a single interface leaves the package edge in place, because Arcan counts the
    edge and not the reference. Measured on pdfbox, only three of eight legal single-class
    candidates had a consumer that named exactly one class across the boundary; the rest named
    2, 2, 3, 5 and 25, and the two that were applied compiled cleanly and moved the smell count
    by zero. Inverting the whole edge at once is the version of the operation that can actually
    close a cycle.

    `max_classes` is a cost ceiling, not a semantic one: an edge carrying more classes than
    this is a merge or a split, not an inversion, and creating thirty interfaces to satisfy a
    detector would be worse code than the smell. Raised from 12 to 25 once the driver began
    inverting the legal SUBSET of a group rather than refusing the whole of it — pdfbox's
    largest edge carries 25 classes and was previously skipped before anything was checked.
    """
    comps = [c.strip() for c in (finding.get("components") or []) if c.strip()]
    scope = [c for c in comps if c in set(facts.packages())]
    if len(scope) < 2:
        scope = (scope + candidate_targets(facts, comps, graph=graph))[:8]
    root_of = {p: spoon_plan.package_root(facts, p) for p in scope}

    out, seen = [], set()
    for consumer in scope:
        for impl_pkg in scope:
            if consumer == impl_pkg or (consumer, impl_pkg) in seen:
                continue
            if root_of.get(consumer) is None or root_of.get(consumer) != root_of.get(impl_pkg):
                continue
            seen.add((consumer, impl_pkg))
            used = implementations_used_by(facts, consumer, impl_pkg, limit=max_classes + 1)
            if not used or len(used) > max_classes:
                continue
            e = spoon_plan.Edit("invertEdge", used[0], consumer, types=list(used))
            if any(spoon_plan._why_not(spoon_plan.Edit("extractInterface", f, consumer), facts)
                   for f in used):
                continue
            out.append(e)
            if len(out) >= limit:
                return out
    return out
