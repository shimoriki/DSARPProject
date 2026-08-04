"""Run the FULL loop over every repository that is not used for training.

Each repo goes through the same pipeline the dashboard runs:

    detect -> plan (all smell types) -> refactor -> re-detect -> re-suggest,
    repeated until a pass stops being safe

Repos whose build system DSARP cannot drive (Gradle, Ant) are reported as
`not_verifiable_unsupported_build` rather than silently producing suggestions with no
verification — that ambiguity is what made a Solr run look like the loop had done nothing.

    py scripts/run_all_repos.py                  # all held-out repos
    py scripts/run_all_repos.py --include-training
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dsarp.config import load_config                                     # noqa: E402
from dsarp.splits.manager import SplitManager                            # noqa: E402
from dsarp.util import write_json                                        # noqa: E402
from dsarp.verification.iterative_loop import run_until_converged        # noqa: E402
from dsarp.verification.openrewrite_loop import detect_build_system      # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detector", default="both")
    ap.add_argument("--max-passes", type=int, default=3, dest="max_passes")
    ap.add_argument("--include-training", action="store_true",
                    help="also run the training repos (normally held out of evaluation)")
    ap.add_argument("--only", nargs="*", help="restrict to these repo ids")
    ap.add_argument("--build", choices=("maven", "gradle"),
                    help="restrict to one build system (Gradle runs are slower)")
    ap.add_argument("--report", default="all_repos_loop.json",
                    help="report filename under data/reports/")
    args = ap.parse_args()

    cfg = load_config("local")
    sm = SplitManager()
    training = set(sm.train) if hasattr(sm, "train") else set()
    repos_dir = cfg.data_dir / "raw" / "repos"
    repos = sorted(p.name for p in repos_dir.iterdir() if p.is_dir()) if repos_dir.exists() else []
    if args.only:
        repos = [r for r in repos if r in args.only]
    elif not args.include_training:
        repos = [r for r in repos if r not in training]

    print(f"[all] {len(repos)} repositories: {', '.join(repos)}\n")
    results = []
    for name in repos:
        path = repos_dir / name
        build = detect_build_system(path)
        if build not in ("maven", "gradle"):
            print(f"  {name:34s} SKIP  {build} project — DSARP drives OpenRewrite through "
                  "its Maven and Gradle plugins only")
            results.append({"repo": name, "build_system": build,
                            "verification_status": "not_verifiable_unsupported_build",
                            "targeted_before": None, "targeted_after": None})
            continue
        if args.build and build != args.build:
            continue
        t0 = time.time()
        try:
            rep = run_until_converged(cfg, name, path, detector=args.detector,
                                      max_passes=args.max_passes)
        except Exception as e:
            print(f"  {name:34s} ERROR {e}")
            results.append({"repo": name, "build_system": build, "error": str(e)})
            continue
        secs = round(time.time() - t0)
        types = rep.get("smell_types_refactored") or []
        print(f"  {name:34s} {rep['passes_accepted']}/{rep['passes_run']} passes  "
              f"targeted {rep['architectural_smells_before']} -> "
              f"{rep['architectural_smells_after']} ({rep['reduction_pct']}%)  "
              f"[{', '.join(types) or 'nothing applicable'}]  {secs}s")
        results.append({"repo": name, "build_system": build,
                        "passes_accepted": rep["passes_accepted"],
                        "passes_run": rep["passes_run"],
                        "targeted_before": rep["architectural_smells_before"],
                        "targeted_after": rep["architectural_smells_after"],
                        "reduction_pct": rep["reduction_pct"],
                        "smell_types_refactored": types,
                        "stop_reason": rep.get("stop_reason"), "seconds": secs})

    ok = [r for r in results if r.get("passes_accepted")]
    by_type: dict = {}
    for r in results:
        for t in r.get("smell_types_refactored") or []:
            by_type[t] = by_type.get(t, 0) + 1
    summary = {"repositories": len(results),
               "refactored_and_verified": len(ok),
               "by_build_system": {b: sum(1 for r in results if r.get("build_system") == b)
                                   for b in {r.get("build_system") for r in results}},
               "unsupported_build": sum(1 for r in results
                                        if r.get("verification_status") ==
                                        "not_verifiable_unsupported_build"),
               "smell_types_refactored_across_repos": by_type,
               "results": results}
    out = cfg.data_dir / "reports" / args.report
    write_json(out, summary)
    print(f"\n[all] {len(ok)}/{len(results)} repositories refactored AND verified")
    print(f"[all] smell types refactored across repos: {by_type}")
    print(f"[all] report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
