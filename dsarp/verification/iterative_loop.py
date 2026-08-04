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
from typing import Any, Dict, List, Optional

from ..config import Config
from ..util import write_json
from .effect_checker import _copy_repo
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


def run_until_converged(cfg: Config, project_id: str, repo_path: Path,
                        detector: str = "both", max_passes: int = 5,
                        strategy: str = "merge_package") -> Dict[str, Any]:
    """Repeat detect -> refactor -> verify, keeping only passes that measurably help."""
    repo_path = Path(repo_path)
    out = cfg.data_dir / "outputs" / project_id
    work = out / "iterative"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    # Iterate on a working copy so the user's checkout is never modified.
    current = _copy_repo(repo_path, work / "pass_0")
    passes: List[Dict[str, Any]] = []
    baseline: Optional[int] = None
    best_by_type: Dict[str, int] = {}

    for i in range(1, max_passes + 1):
        rep = refactor_with_openrewrite_and_verify(
            cfg, f"{project_id}__pass{i}", current, detector=detector, strategy=strategy,
            keep_copy=True)

        b_by = rep.get("by_type_before") or {}
        a_by = rep.get("by_type_after") or {}
        # `verification_status == "verified"` only means SOME tool measured both sides. If the
        # build broke, Arcan drops out and the before/after scores are then computed over a
        # different set of tools — a smaller number that reflects lost measurement, not lost
        # smells. Accepting a pass therefore also requires a compiling build.
        built = rep.get("build_after_refactoring") == "compiled"
        verified = rep.get("verification_status") == "verified" and built
        before_score = score(b_by)
        after_score = score(a_by) if verified else None
        if baseline is None:
            baseline, best_by_type = before_score, b_by

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
        if after_score is None or after_score >= before_score:
            record.update(accepted=False,
                          stop_reason=f"no improvement ({before_score} -> {after_score} "
                                      "architectural smells); rolled back and stopped")
            passes.append(record)
            break

        # Accept: the refactored copy becomes the input to the next pass.
        refactored = Path(rep.get("refactored_copy") or "")
        keep = work / f"pass_{i}"
        if refactored.exists():
            shutil.rmtree(keep, ignore_errors=True)
            shutil.move(str(refactored), str(keep))
            current = keep
        record.update(accepted=True, stop_reason=None)
        best_by_type = a_by
        passes.append(record)

    accepted = [p for p in passes if p.get("accepted")]
    final_score = accepted[-1]["score_after"] if accepted else baseline
    report = {
        "project_id": project_id, "detector": detector, "strategy": strategy,
        "passes_run": len(passes), "passes_accepted": len(accepted),
        "architectural_smells_before": baseline,
        "architectural_smells_after": final_score,
        "removed": (baseline - final_score) if baseline is not None else None,
        "reduction_pct": (round(100.0 * (baseline - final_score) / baseline, 1)
                          if baseline else 0.0),
        "smell_types_refactored": sorted({t for p in accepted
                                          for t in p["smell_types_refactored"]}),
        "final_by_type": best_by_type,
        "stop_reason": passes[-1].get("stop_reason") if passes else "no passes run",
        "refactored_source": str(current) if accepted else None,
        "passes": passes,
    }
    write_json(out / "iterative_loop_report.json", report)
    return report
