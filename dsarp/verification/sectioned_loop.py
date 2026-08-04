"""Verify a large repository MODULE BY MODULE instead of all at once.

Whole-repo runs failed on exactly the big projects: log4j2 (186 plans in one pass), Spark and
commons-io all broke the build, while small repos succeeded. Two things go wrong at scale —
one bad plan among many invalidates the entire pass, and a single compile of a 40-module
project is slow enough that a failure costs an hour before it is visible.

Running per module fixes both. Each module is a smaller, independent scope with its own
`pom.xml`, so its plans are few, its build is isolated, and a module that breaks does not
discard the modules that worked.

Modules whose refactoring does not compile are simply not counted — the same rollback rule
as the whole-repo loop, applied at a finer grain.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import Config
from ..util import write_json
from .iterative_loop import run_until_converged


def find_modules(repo_path: Path, min_java: int = 12) -> List[Path]:
    """Buildable submodules that hold enough Java to be worth refactoring separately.

    A module needs its own pom.xml (so Maven can build it alone) and real production
    sources. Tiny modules are skipped: the per-module overhead is a full detect+build cycle,
    which is not worth paying for a handful of classes.
    """
    repo_path = Path(repo_path)
    out = []
    for pom in sorted(repo_path.glob("*/pom.xml")) + sorted(repo_path.glob("*/*/pom.xml")):
        mod = pom.parent
        src = mod / "src" / "main" / "java"
        if not src.is_dir():
            continue
        if sum(1 for _ in src.rglob("*.java")) < min_java:
            continue
        # skip a module nested inside one already selected — the parent build covers it
        if any(str(mod).startswith(str(prev) + "\\") or str(mod).startswith(str(prev) + "/")
               for prev in out):
            continue
        out.append(mod)
    return out


def run_sectioned(cfg: Config, project_id: str, repo_path: Path, detector: str = "both",
                  max_passes: int = 2, max_modules: int = 0,
                  min_java: int = 12) -> Dict[str, Any]:
    """Run the iterative loop on each module; aggregate what actually verified."""
    repo_path = Path(repo_path)
    modules = find_modules(repo_path, min_java=min_java)
    if max_modules:
        modules = modules[:max_modules]
    out = cfg.data_dir / "outputs" / project_id

    if not modules:
        report = {"project_id": project_id, "mode": "sectioned", "modules": 0,
                  "note": "no submodule has its own pom.xml and enough Java sources; "
                          "this repository can only be refactored as a whole"}
        write_json(out / "sectioned_loop_report.json", report)
        return report

    print(f"[sectioned] {project_id}: {len(modules)} module(s)")
    results: List[Dict[str, Any]] = []
    for i, mod in enumerate(modules, 1):
        name = mod.name
        t0 = time.time()
        try:
            rep = run_until_converged(cfg, f"{project_id}__mod_{name}", mod,
                                      detector=detector, max_passes=max_passes)
        except Exception as e:
            print(f"  [{i}/{len(modules)}] {name:32s} ERROR {str(e)[:60]}")
            results.append({"module": name, "error": str(e)[:200]})
            continue
        secs = round(time.time() - t0)
        types = rep.get("smell_types_refactored") or []
        ok = rep.get("passes_accepted", 0) > 0
        print(f"  [{i}/{len(modules)}] {name:32s} "
              f"{rep['passes_accepted']}/{rep['passes_run']}  "
              f"{rep['architectural_smells_before']}->{rep['architectural_smells_after']} "
              f"({rep['reduction_pct']}%)  {secs}s"
              + (f"  [{', '.join(types)}]" if ok else ""))
        results.append({"module": name, "passes_accepted": rep["passes_accepted"],
                        "passes_run": rep["passes_run"],
                        "targeted_before": rep["architectural_smells_before"],
                        "targeted_after": rep["architectural_smells_after"],
                        "reduction_pct": rep["reduction_pct"],
                        "smell_types_refactored": types,
                        "stop_reason": rep.get("stop_reason"), "seconds": secs})

    improved = [r for r in results if r.get("passes_accepted")]
    before = sum(r.get("targeted_before") or 0 for r in results)
    after = sum(r.get("targeted_after") if r.get("targeted_after") is not None
                else (r.get("targeted_before") or 0) for r in results)
    types: Dict[str, int] = {}
    for r in improved:
        for t in r.get("smell_types_refactored") or []:
            types[t] = types.get(t, 0) + 1
    report = {
        "project_id": project_id, "mode": "sectioned", "detector": detector,
        "modules": len(results), "modules_improved": len(improved),
        "targeted_before": before, "targeted_after": after,
        "removed": before - after,
        "reduction_pct": round(100.0 * (before - after) / before, 1) if before else 0.0,
        "smell_types_refactored": types, "results": results,
    }
    write_json(out / "sectioned_loop_report.json", report)
    print(f"[sectioned] {project_id}: {len(improved)}/{len(results)} modules improved, "
          f"targeted {before} -> {after} ({report['reduction_pct']}%)")
    return report
