"""Apply a trained model's refactoring suggestions in batches, and measure each batch with Arcan.

Scope rule, and it is the whole point: nothing here invents a refactoring. The operations come
from the model's own suggestion CSV, concretized by the DSARP-OpenRewrite repository's own
`openrewrite/generate_recipes.py`, which acts on `Move Class` and derives source and destination
by analysing the subject itself. This module decides only WHICH of those candidates to attempt
and in what order, and it measures the result.

Why batches rather than one run. Applying all 86 Tika candidates at once produced a tree that
would not build, and a smell count from a tree that did not build is not a result: Arcan read 176
against a 260 baseline purely because 91 modules had been skipped. A batch is small enough that
one bad move does not void the other eighty, and each batch yields its own before/after delta.

Why a viability filter is not scope creep. The generator decides a move from reciprocal package
dependencies alone and performs no visibility analysis, so it happily proposes moving a class
that uses package-private members of its neighbours. Those moves cannot compile anywhere, and
making them compile would mean widening somebody else's API. This project already screens for
exactly that -- `move_blockers`, `package_private_export_blockers`, `protected_nested_blockers`,
all written against log4j-core failing this way -- so the screen is reused rather than rebuilt.
Skipping a move that cannot build is what "do not break the repository" means; it adds nothing.

Measured on Tika before batching existed, as the reason each guard is here:
  * a nested-type import suppressed its outer type's import  -> fixed in java_text.names_fqn
  * ChangeType deletes `import static Moved.MEMBER`          -> repaired per batch
  * package-private access across the new boundary           -> screened out, unrepairable
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..openrewrite.runner import run_recipe
from ..refactoring.java_text import repair_static_imports

RECIPE_NAME = "generated.architecture.ApplyAllCandidates"


def concrete_moves(manifest_path: Path) -> List[Dict[str, Any]]:
    """The `ready_for_dry_run` candidates the generator produced, in its own ranked order."""
    doc = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    records = doc if isinstance(doc, list) else doc.get("records", [])
    out = []
    for r in records:
        if not isinstance(r, dict) or r.get("status") != "ready_for_dry_run":
            continue
        out.append({"id": r.get("prediction_id"), "smell": r.get("architecture_smell"),
                    "old": r.get("source_type"), "new": r.get("destination_type"),
                    "risk": r.get("risk_level"),
                    "affected": r.get("affected_elements") or []})
    return out


def screen(repo: Path, moves: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Split the candidates into those that can compile elsewhere and those that cannot.

    Three questions, all about visibility across the new package boundary:
      * what does the moving class need FROM its package that it will lose;
      * what does the package need FROM the moving class that it will lose;
      * which protected nested types of its siblings does it use.
    """
    from ..refactoring.spoon_plan import (package_private_export_blockers,
                                          protected_nested_blockers)
    from ..refactoring.strategies import SourceFacts
    facts = SourceFacts(Path(repo))
    viable, blocked = [], []
    for m in moves:
        fqn = m["old"]
        reasons: List[str] = []
        try:
            reasons += list(facts.move_blockers(fqn) or [])
            reasons += package_private_export_blockers(facts, fqn)
            reasons += protected_nested_blockers(facts, fqn)
        except Exception as exc:                       # a parse failure is not a verdict
            reasons.append("screen failed: %s" % str(exc)[:120])
        if reasons:
            blocked.append({**m, "blockers": reasons[:3]})
        else:
            viable.append(m)
    return {"viable": viable, "blocked": blocked}


def module_index(repo: Path, moves: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """For each moved type, the reactor modules that declare or reference it.

    Built in a single pass over the sources, because asking per move re-reads the whole tree
    once per candidate and there are hundreds of them.
    """
    repo = Path(repo)
    by_simple: Dict[str, List[str]] = {}
    for m in moves:
        by_simple.setdefault(m["old"].rsplit(".", 1)[-1], []).append(m["old"])
    mods = [p.parent for p in repo.rglob("pom.xml")
            if "/target/" not in p.as_posix() and p.parent != repo]
    hits: Dict[str, set] = {m["old"]: set() for m in moves}
    for mod in mods:
        rel = mod.relative_to(repo).as_posix()
        for java in mod.rglob("*.java"):
            if "/target/" in java.as_posix():
                continue
            try:
                text = java.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for simple, fqns in by_simple.items():
                if simple in text:
                    for f in fqns:
                        hits[f].add(rel)
    return {k: sorted(v) for k, v in hits.items()}


def pack_batches(index: Dict[str, List[str]], moves: List[Dict[str, Any]],
                 max_moves: int = 25, max_modules: int = 28) -> List[List[Dict[str, Any]]]:
    """Group moves so that each batch's reactor stays small enough to rewrite in memory.

    Size alone is the wrong bound. A batch of 25 moves whose types are referenced across 71
    modules needs the whole repository in the LST and dies on a 2 GB heap, while a batch of the
    same size confined to 18 modules runs fine. So batches are packed against the union of
    modules they touch, narrowest types first, and a single type that alone exceeds the cap gets
    a batch of its own rather than being dropped.
    """
    ordered = sorted(moves, key=lambda m: (len(index.get(m["old"], [])), m["old"]))
    batches: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    cur_mods: set = set()
    for m in ordered:
        mods = set(index.get(m["old"], []))
        if cur and (len(cur) >= max_moves or len(cur_mods | mods) > max_modules):
            batches.append(cur)
            cur, cur_mods = [], set()
        cur.append(m)
        cur_mods |= mods
    if cur:
        batches.append(cur)
    return batches


def modules_touching(repo: Path, moves: List[Dict[str, Any]]) -> List[str]:
    """Reactor modules that declare or reference any type in this batch.

    OpenRewrite holds the LST for everything it parses in memory at once, so running it over a
    whole large repository needs a heap this machine does not reliably have: all three Tika
    batches died with an out-of-memory on a 2 GB heap, which is what is left when the desktop is
    in use. Restricting the reactor keeps the heap proportional to the section.

    The modules selected are the one that OWNS each moved type plus every module that NAMES it.
    Scoping to the owner alone is what makes sectioned rewriting unsafe: a reference in a module
    outside the selection is never updated, and the build breaks on a type that no longer exists.
    """
    repo = Path(repo)
    names = set()
    for m in moves:
        names.add(m["old"])
        names.add(m["old"].rsplit(".", 1)[-1])
    poms = [p.parent for p in repo.rglob("pom.xml")
            if "/target/" not in p.as_posix() and p.parent != repo]
    hits = []
    for mod in poms:
        found = False
        for java in mod.rglob("*.java"):
            if "/target/" in java.as_posix():
                continue
            try:
                text = java.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if any(n in text for n in names):
                found = True
                break
        if found:
            hits.append(mod.relative_to(repo).as_posix())
    # drop a module that is an ancestor of another selected one; -pl takes the leaves
    return sorted(h for h in hits
                  if not any(o != h and o.startswith(h + "/") for o in hits))


def _write_recipe(repo: Path, moves: List[Dict[str, Any]]) -> None:
    lines = ["---", "type: specs.openrewrite.org/v1beta/recipe", "name: " + RECIPE_NAME,
             "displayName: Model Move Class suggestions, one batch",
             "description: >-",
             "  One batch of the model's own Move Class suggestions, concretized by the "
             "repository's generator.", "recipeList:"]
    for m in moves:
        lines += ["  - org.openrewrite.java.ChangeType:",
                  "      oldFullyQualifiedTypeName: " + m["old"],
                  "      newFullyQualifiedTypeName: " + m["new"],
                  "      ignoreDefinition: false"]
    (repo / "rewrite.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_batch(baseline: Path, work: Path, moves: List[Dict[str, Any]], label: str,
              measure_script: Path, exclude_modules: Optional[List[str]] = None,
              python: Optional[str] = None, timeout: int = 10800) -> Dict[str, Any]:
    """Apply one batch to a fresh copy of the baseline, build it, and measure it.

    A fresh copy per batch keeps the deltas attributable: every batch is measured against the
    same starting tree, so one batch's damage cannot be charged to the next.
    """
    python = python or sys.executable
    work = Path(work)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    tree = work / "tree"
    shutil.copytree(baseline, tree, ignore=shutil.ignore_patterns("target", ".git"))
    _write_recipe(tree, moves)

    row: Dict[str, Any] = {"label": label, "moves": len(moves),
                           "types": [m["old"] for m in moves]}
    t0 = time.time()
    scope = modules_touching(tree, moves)
    # An exclusion cannot ride alongside a positive selection: Maven answers `-pl a,b,!c` with
    # "Could not find the selected project in the reactor: c" when c was never selected. With a
    # scope in hand the exclusions are subtracted from it instead.
    banned = {e.lstrip("!") for e in (exclude_modules or [])}
    if scope:
        selection = [m for m in scope if m not in banned
                     and m.rsplit("/", 1)[-1] not in banned]
    else:
        selection = list(exclude_modules or [])
    row["reactor_modules"] = len(selection)
    res = run_recipe(tree, recipe_name=RECIPE_NAME, log_path=work / "rewrite.log",
                     modules=selection or None, timeout=timeout)
    row["apply_status"] = res.get("status")
    row["files_changed"] = len(res.get("changed_files") or [])
    if res.get("status") != "changed":
        row.update(ok=False, why="apply did not change anything: %s" % res.get("status"),
                   secs=round(time.time() - t0))
        return row

    repaired = repair_static_imports(baseline, tree, [(m["old"], m["new"]) for m in moves])
    row["static_imports_repaired"] = sum(len(v) for v in repaired.values())

    proc = subprocess.run([python, str(measure_script), str(tree), str(work / "measure"), label],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)
    try:
        measured = json.loads((work / "measure" / "result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        row.update(ok=False, why="measurement produced no result.json",
                   tail=(proc.stdout or "")[-400:], secs=round(time.time() - t0))
        return row
    row["build"] = measured.get("build")
    row["class_files"] = measured.get("class_files")
    row["arcan"] = measured.get("arcan")
    row["secs"] = round(time.time() - t0)
    return row


def verdict(batch: Dict[str, Any], base_build: Dict[str, Any],
            base_smells: int, tolerance: int = 0) -> Dict[str, Any]:
    """Is this batch's smell count comparable to the baseline's, and what is the delta?

    A batch is only allowed to report a delta when its build reached the same module set as the
    baseline. Anything less and the count is measured over different code; that is the failure
    that produced an apparent 32% improvement from a tree with 91 modules missing.
    """
    b = batch.get("build") or {}
    arc = batch.get("arcan") or {}
    want = (base_build or {}).get("modules_success")
    got = b.get("modules_success")
    if not arc.get("ok"):
        return {"comparable": False, "why": "arcan did not run"}
    if want is not None and got is not None and got < want - tolerance:
        return {"comparable": False,
                "why": "built %s of the baseline's %s modules; the counts are over different "
                       "code" % (got, want),
                "smells_raw": arc.get("smells")}
    delta = (arc.get("smells") or 0) - base_smells
    # Signed as a CHANGE, not as a saving. Negating it here printed "delta +23 (-8.85%)" for a
    # batch that added 23 smells, which reads as an 8.85% improvement and is the opposite.
    # Negative pct_change means fewer smells; removed_pct is 0 unless the count actually fell.
    return {"comparable": True, "before": base_smells, "after": arc.get("smells"),
            "delta": delta,
            "pct_change": round(100.0 * delta / base_smells, 2) if base_smells else None,
            "removed_pct": round(-100.0 * delta / base_smells, 2)
                           if base_smells and delta < 0 else 0.0}


def chunk(items: List[Any], size: int) -> List[List[Any]]:
    return [items[i:i + size] for i in range(0, len(items), size)]
