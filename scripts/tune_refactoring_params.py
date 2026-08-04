"""SkillOpt-style tuning of the refactoring policy against a MEASURED reward.

SkillOpt treats a skill file as trainable parameters, proposes edits, and keeps only those
that pass a validation gate. The same shape applies here, with one advantage most SkillOpt
setups lack: the gate is fully automatic and objective, because the closed loop already
reports whether the refactored code still builds and how the real tools' smell counts moved.

    parameters   configs/refactoring_params.json  (dsarp.refactoring.params)
    candidate    one value changed from the incumbent (coordinate descent)
    reward       mean architectural smells removed per repo, over repos where the
                 refactored code STILL BUILDS
    gate         any candidate that breaks a build on any repo scores -inf and is rejected
    feedback     rejected candidates are recorded with the reason, so the search log shows
                 WHY a setting was refused, not just that it lost

Correctness-relevant parameters (`dead_code_max_references`,
`encapsulate_max_external_readers`) are deliberately excluded from SEARCH_SPACE: raising
them buys a better score by deleting or hiding code that is actually used. The gate should
not have to be the only thing standing between the tuner and that trade.

Usage
    py scripts/tune_refactoring_params.py --repos apache-commons-validator apache-commons-codec
    py scripts/tune_refactoring_params.py --repos ... --deploy      # write the winner
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dsarp.config import load_config                                    # noqa: E402
from dsarp.refactoring.params import SEARCH_SPACE, RefactoringParams    # noqa: E402
from dsarp.repositories.manager import RepositoryManager                # noqa: E402
from dsarp.util import write_json                                       # noqa: E402
from dsarp.verification.iterative_loop import run_until_converged, score  # noqa: E402

REJECTED = float("-inf")


def evaluate(cfg, params: RefactoringParams, repos, detector="both", max_passes=2):
    """Run the loop on every repo under `params`; return (reward, per-repo detail).

    Reward = mean architectural smells removed. A build failure anywhere is fatal: a policy
    that produces code which does not compile is not a better policy at any score.
    """
    params.save()                       # strategies read the file at import/plan time
    per_repo, removed = {}, []
    for name in repos:
        repo_path = RepositoryManager(cfg.data_dir).path_for(name)
        if not repo_path.exists():
            per_repo[name] = {"status": "missing_checkout"}
            continue
        t0 = time.time()
        rep = run_until_converged(cfg, f"tune__{name}", repo_path,
                                  detector=detector, max_passes=max_passes)
        broke = any(p.get("verification_status") == "unverified_build_broken"
                    for p in rep["passes"])
        detail = {"before": rep["architectural_smells_before"],
                  "after": rep["architectural_smells_after"],
                  "removed": rep["removed"], "passes_accepted": rep["passes_accepted"],
                  "build_broken": broke, "seconds": round(time.time() - t0, 1)}
        per_repo[name] = detail
        if broke:
            return REJECTED, {**per_repo, "_rejected": f"{name}: refactored code did not build"}
        removed.append(rep["removed"] or 0)
    if not removed:
        return REJECTED, {**per_repo, "_rejected": "no repository could be evaluated"}
    return sum(removed) / len(removed), per_repo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos", nargs="+", required=True)
    ap.add_argument("--detector", default="both")
    ap.add_argument("--max-passes", type=int, default=2)
    ap.add_argument("--deploy", action="store_true",
                    help="write the winning parameters to configs/refactoring_params.json")
    args = ap.parse_args()

    cfg = load_config("local")
    incumbent = RefactoringParams.load()
    original = RefactoringParams.load()
    trials = []

    print(f"[tune] baseline params: {incumbent.as_dict()}")
    best_reward, best_detail = evaluate(cfg, incumbent, args.repos, args.detector,
                                        args.max_passes)
    print(f"[tune] baseline reward = {best_reward} {best_detail}")
    trials.append({"params": incumbent.as_dict(), "reward": best_reward,
                   "detail": best_detail, "kind": "baseline"})

    # Coordinate descent: change one knob at a time and keep only strict improvements.
    for knob, values in SEARCH_SPACE.items():
        current = getattr(incumbent, knob)
        for value in values:
            if value == current:
                continue
            candidate = replace(incumbent, **{knob: value})
            reward, detail = evaluate(cfg, candidate, args.repos, args.detector,
                                      args.max_passes)
            accepted = reward > best_reward
            status = ("ACCEPTED" if accepted else
                      "REJECTED (gate)" if reward == REJECTED else "rejected (no gain)")
            print(f"[tune] {knob}={value}: reward={reward} -> {status}"
                  + (f"  {detail.get('_rejected')}" if detail.get("_rejected") else ""))
            trials.append({"params": candidate.as_dict(), "reward": reward, "detail": detail,
                           "kind": f"{knob}={value}", "accepted": accepted,
                           "rejection_reason": detail.get("_rejected")})
            if accepted:
                best_reward, incumbent = reward, candidate

    improved = incumbent.as_dict() != original.as_dict()
    report = {"baseline": original.as_dict(), "winner": incumbent.as_dict(),
              "baseline_reward": trials[0]["reward"], "best_reward": best_reward,
              "improved": improved, "repos": args.repos, "trials": trials}
    out = cfg.data_dir / "reports" / "refactoring_param_tuning.json"
    write_json(out, report)

    if args.deploy and improved:
        incumbent.save()
        print(f"[tune] DEPLOYED {incumbent.as_dict()}")
    else:
        original.save()                 # restore; evaluate() has been overwriting the file
        print("[tune] no improvement found; baseline restored"
              if not improved else "[tune] winner found (use --deploy to write it)")
    print(f"[tune] report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
