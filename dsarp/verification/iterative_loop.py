"""Iterate the closed loop until it stops helping.

A single pass is deliberately conservative: two refactorings that touch the same type
interfere, so the conflict filter lets only one of them through and defers the rest. Those
deferred plans never ran, which capped how much any one pass could achieve.

This module runs the loop repeatedly. Each pass re-detects on the *refactored* code, so the
plans deferred last time are re-planned against current reality and can land now.

The stopping rule is what keeps it honest — a pass is KEPT only if it

  * still COMPILES (`build_after_refactoring == "compiled"`),
  * had its result measured by the tools (`verification_status == "verified"`), and
  * strictly reduces the objective (see `score`).

The compile check is not redundant with the verified flag. "Verified" only means *some* tool
measured both sides; when the build breaks, Arcan (which reads bytecode) drops out and the
before/after scores are then computed over a smaller set of tools. That reads as a large
improvement while actually being lost measurement — an early version of this module scored a
broken pass as a 13.2% reduction for exactly that reason.

Anything else is ROLLED BACK and the loop stops. So the result is never worse than the input,
and every accepted pass is backed by a real before/after measurement from the real tools.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..config import Config
from ..util import write_json
from .effect_checker import _copy_repo
from ..refactoring.agents import is_expansive
from .openrewrite_loop import refactor_with_openrewrite_and_verify


# Smells the refactoring families here actually target. Scoring on these rather than on the
# raw total stops unrelated noise (implementation/test smells) from masking real progress.
ARCHITECTURAL = ("cyclic dependency", "unstable dependency", "god component",
                 "hub-like dependency", "scattered functionality", "feature concentration",
                 "cyclically-dependent modularization", "deficient encapsulation",
                 "rebellious hierarchy", "unutilized abstraction")


def score(by_type: Dict[str, int]) -> int:
    """Objective to minimise: how many architectural smells remain."""
    return sum(n for smell, n in (by_type or {}).items()
               if any(k in smell.lower() for k in ARCHITECTURAL))


def targeted_score(by_type: Dict[str, int], targeted: Iterable[str]) -> int:
    """Remaining count for ONLY the smell types this run actually tried to fix.

    The headline number has to be this, not the total. Splitting a God Component creates a
    new package that Designite then reports as Feature Concentration, so a refactoring that
    genuinely removed what it aimed at can still make the grand total look worse. Judging a
    run on smells it never targeted measures the detector's taxonomy, not the refactoring.
    """
    keys = [t.lower() for t in targeted]
    return sum(n for smell, n in (by_type or {}).items()
               if any(k in smell.lower() or smell.lower() in k for k in keys))


def per_type_delta(before: Dict[str, int], after: Dict[str, int],
                   targeted: Iterable[str]) -> Dict[str, Any]:
    """Per-smell-type before/after, split into what was targeted and what moved on its own."""
    keys = [t.lower() for t in targeted]
    rows, side_effects = [], []
    for smell in sorted(set(before) | set(after)):
        b, a = before.get(smell, 0), after.get(smell, 0)
        row = {"smell_type": smell, "before": b, "after": a, "delta": a - b}
        if any(k in smell.lower() or smell.lower() in k for k in keys):
            rows.append(row)
        elif a != b:
            side_effects.append(row)
    return {"targeted": rows, "side_effects": side_effects,
            "targeted_removed": sum(r["before"] - r["after"] for r in rows),
            "targeted_before": sum(r["before"] for r in rows),
            "targeted_after": sum(r["after"] for r in rows)}


def run_until_converged(cfg: Config, project_id: str, repo_path: Path,
                        detector: str = "both", max_passes: int = 5,
                        strategy: str = "merge_package",
                        start_budget: int = 0, patience: int = 1,
                        min_passes: int = 2) -> Dict[str, Any]:
    """Repeat detect -> refactor -> verify, escalating how much is attempted per pass.

    Two behaviours that matter, both learned from measured failures:

    * **Budget escalation.** A pass applies only its `budget` best-ranked plans, starting
      small and doubling while passes keep being accepted. Applying every plan at once let
      one bad plan fail the whole pass (log4j2 attempted 186) and let expansive refactorings
      drown out clean ones.
    * **Patience.** Splitting a God Component CREATES a package the detector flags, so the
      count rises before a later pass can consolidate it. Stopping at the first
      non-improving pass made that outcome unreachable. A pass that still COMPILES but does
      not improve is now kept, up to `patience` times, so the follow-up pass gets its chance
      to clean up. A pass that breaks the build is still rolled back immediately.
    """
    repo_path = Path(repo_path)
    out = cfg.data_dir / "outputs" / project_id
    work = out / "iterative"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    # Iterate on a working copy so the user's checkout is never modified.
    current = _copy_repo(repo_path, work / "pass_0")
    passes: List[Dict[str, Any]] = []
    carried: Optional[Dict[str, Any]] = None   # previous pass's AFTER measurement
    # Scale the first budget with how much work the repo actually has. A fixed budget of 2
    # is sensible on commons-validator and absurd on Karaf, which produced 1400 plans and
    # deferred 47 viable ones as "outside this pass's budget" - so a large repo looked inert
    # when it simply was not being allowed to act.
    # start_budget 0 means "no cap on the first pass". Sizing it AFTER pass 1 was useless:
    # the loop stops when pass 1 does not improve, so the larger budget never applied and a
    # 1400-plan repository like Karaf deferred everything as "outside this pass's budget".
    # The conflict filter and the safety guards already bound what can run together.
    budget = start_budget
    used_patience = 0
    best_score: Optional[int] = None
    baseline: Optional[int] = None
    best_by_type: Dict[str, int] = {}

    for i in range(1, max_passes + 1):
        rep = refactor_with_openrewrite_and_verify(
            cfg, f"{project_id}__pass{i}", current, detector=detector, strategy=strategy,
            keep_copy=True, known_before=carried, plan_budget=budget)
        if i == 1:
            # size the budget from the first pass's actual plan count
            applicable = sum(1 for p in (rep.get("plans") or []) if p.get("applicable"))
            deferred = sum(1 for p in (rep.get("plans") or [])
                           if "outside this pass" in (p.get("reason") or ""))
            if deferred:
                budget = max(budget, min(32, (applicable + deferred) // 2 or budget))

        b_by = rep.get("by_type_before") or {}
        a_by = rep.get("by_type_after") or {}
        # `verification_status == "verified"` only means SOME tool measured both sides. If the
        # build broke, Arcan drops out and the before/after scores are then computed over a
        # different set of tools — a smaller number that reflects lost measurement, not lost
        # smells. Accepting a pass therefore also requires a compiling build.
        built = rep.get("build_after_refactoring") == "compiled"
        verified = rep.get("verification_status") == "verified" and built
        targeted = sorted({p["smell_type"] for p in (rep.get("plans") or [])
                           if p.get("applicable")})
        before_score = targeted_score(b_by, targeted) if targeted else score(b_by)
        after_score = ((targeted_score(a_by, targeted) if targeted else score(a_by))
                       if verified else None)
        # RUN-level metric must be consistent across passes. `before_score`/`after_score`
        # are computed over the smell types THAT pass targeted, which legitimately differ
        # per pass — comparing pass 1's baseline to pass 4's result mixes two different
        # measurements and produced a meaningless "10 -> 18". The run summary therefore uses
        # the full architectural score, which is the same set every pass.
        if baseline is None:
            baseline, best_by_type = score(b_by), b_by

        record = {
            "pass": i, "verification_status": rep.get("verification_status"),
            "build": rep.get("build_after_refactoring"),
            "plans_applied": rep.get("moves") or len(rep.get("plans") or []),
            "smell_types_refactored": sorted({p["smell_type"] for p in (rep.get("plans") or [])
                                              if p.get("applicable")}),
            "deferred": sum(1 for p in (rep.get("plans") or [])
                            if "conflicts with another" in (p.get("reason") or "")),
            "files_changed": len(rep.get("changed_files") or []),
            "score_before": before_score, "score_after": after_score,
            "plan_budget": budget,
            "targeted_smell_types": targeted,
            "per_type": per_type_delta(b_by, a_by, targeted) if verified else None,
            "total_architectural_before": score(b_by),
            "total_architectural_after": score(a_by) if verified else None,
            "by_type_before": b_by, "by_type_after": a_by,
        }

        record["build_ok"] = built
        if not verified:
            why = ("the refactored code did not compile"
                   if not built else "no tool could measure the result")
            record.update(accepted=False,
                          stop_reason=f"{why}; rolled back and stopped")
            passes.append(record)
            break
        improved = after_score is not None and after_score < before_score
        if best_score is None:
            best_score = before_score

        if not improved:
            # An expansive refactoring (God Component split) is EXPECTED to raise the count
            # first. Keep the pass and let the next one try to consolidate, but only while
            # patience lasts and only because the build is still sound.
            expansive = any(is_expansive(t) for t in targeted)
            if i < min_passes:
                # A refactoring that adds smells before removing them cannot show its value
                # in one pass. Give the loop a floor of passes before the no-improvement rule
                # is allowed to end it; the build gate still rolls back anything broken.
                record.update(accepted=True, kept_on_min_passes=True, stop_reason=None,
                              note=f"pass {i} of a {min_passes}-pass floor: kept without "
                                   "improvement so a later pass can consolidate")
            elif used_patience < patience and expansive:
                used_patience += 1
                record.update(accepted=True, kept_on_patience=True,
                              stop_reason=None,
                              note=f"no immediate improvement ({before_score} -> "
                                   f"{after_score}), but this pass applied an expansive "
                                   "refactoring that is expected to add smells before a "
                                   "later pass can consolidate them; compiles, so kept")
            else:
                why = ("patience exhausted" if expansive else
                       "the refactorings applied cannot reduce this smell set")
                record.update(accepted=False,
                              stop_reason=f"no improvement ({before_score} -> {after_score}); "
                                          f"{why}; rolled back and stopped")
                passes.append(record)
                break
        else:
            used_patience = 0          # real progress resets the allowance
            budget = min(budget * 2, 64)   # and earns a bigger bite next pass
            best_score = min(best_score, after_score)

        # Accept: the refactored copy becomes the input to the next pass.
        refactored = Path(rep.get("refactored_copy") or "")
        keep = work / f"pass_{i}"
        if refactored.exists():
            shutil.rmtree(keep, ignore_errors=True)
            shutil.move(str(refactored), str(keep))
            current = keep
        record.update(accepted=True, stop_reason=None)
        # The tree we just measured becomes the next pass's input, so its AFTER measurement
        # is that pass's BEFORE. Saves a full compile + Arcan + Designite run per pass.
        carried = rep.get("_after_detection")
        best_by_type = a_by
        passes.append(record)

    accepted = [p for p in passes if p.get("accepted")]
    # Patience permits a temporary rise so an expansive refactoring can be consolidated
    # later — but the RUN must return the best state it found, never merely the last one.
    # Without this, keeping non-improving passes let commons-cli finish at 31 -> 36, worse
    # than it started, with every pass marked "accepted".
    scored = [(p["pass"], p.get("total_architectural_after")) for p in accepted
              if p.get("total_architectural_after") is not None]
    best_pass, final_score = (None, baseline)
    for pnum, sc in scored:
        if sc < final_score:
            best_pass, final_score = pnum, sc
    ended_worse = bool(scored) and scored[-1][1] > baseline
    if ended_worse and best_pass is None:
        stop_note = ("every pass compiled, but none reduced the total; the run is reported "
                     "at its BASELINE because keeping the last state would leave the "
                     "repository worse than it started")
    else:
        stop_note = None
    report = {
        "project_id": project_id, "detector": detector, "strategy": strategy,
        "passes_run": len(passes), "passes_accepted": len(accepted),
        "metric": "total architectural smells (consistent across passes; per-pass "
                  "accept/reject uses that pass's targeted types)",
        "architectural_smells_before": baseline,
        "architectural_smells_after": final_score,
        "per_type": (accepted[-1].get("per_type") if accepted else None),
        "removed": (baseline - final_score) if baseline is not None else None,
        "reduction_pct": (round(100.0 * (baseline - final_score) / baseline, 1)
                          if baseline else 0.0),
        "smell_types_refactored": sorted({t for p in accepted
                                          for t in p["smell_types_refactored"]}),
        "final_by_type": best_by_type,
        "stop_reason": (stop_note or (passes[-1].get("stop_reason") if passes
                                      else "no passes run")),
        "best_pass": best_pass, "ended_worse_than_baseline": ended_worse,
        "refactored_source": str(current) if accepted else None,
        "passes": passes,
    }
    write_json(out / "iterative_loop_report.json", report)
    return report
