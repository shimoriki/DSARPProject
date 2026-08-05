"""Test the outcome ledger on repositories it was never built from.

The ledger currently learns from the same runs it then filters, which is fitting and
evaluating on one dataset. Its three refusals are well supported — 4 to 11 verified runs
each, consistent direction — but "we measured this" and "we learned something that
generalises" are different claims, and only held-out data separates them.

This builds the ledger from a TRAINING set of repositories and checks its predictions
against a HELD-OUT set it never saw:

    for each (smell, refactoring) the training ledger calls effective / useless / harmful,
    does the held-out data agree?

A prediction counts as correct when the sign of the held-out mean effect matches the
training verdict. Disagreement is the interesting result — it means the ledger has learned a
repository-specific quirk rather than something about the refactoring.

    py scripts/validate_ledger.py --holdout apache-commons-codec apache-commons-text
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dsarp.config import load_config                                    # noqa: E402
from dsarp.refactoring.outcomes import MIN_RUNS, summarise              # noqa: E402
from dsarp.util import write_json                                       # noqa: E402


def ledger_from(paths):
    """Aggregate (smell, refactoring) -> effect over a specific set of report files."""
    import collections
    stat = collections.defaultdict(lambda: {"runs": 0, "reduced": 0, "net": 0})
    for f in paths:
        try:
            r = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if r.get("build_after_refactoring") != "compiled":
            continue
        delta = r.get("delta_by_type") or {}
        for p in r.get("plans") or []:
            if not p.get("applicable"):
                continue
            d = delta.get(p.get("smell_type"))
            if d is None:
                continue
            s = stat[(p["smell_type"], p.get("refactoring") or "?")]
            s["runs"] += 1
            s["net"] += d
            s["reduced"] += 1 if d < 0 else 0
    return dict(stat)


def verdict(entry):
    if entry["runs"] < MIN_RUNS:
        return "too few runs"
    mean = entry["net"] / entry["runs"]
    if mean > 0:
        return "counterproductive"
    return "no measured benefit" if entry["reduced"] == 0 else "effective"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", nargs="+", required=True,
                    help="repository ids the ledger must NOT be built from")
    args = ap.parse_args()

    cfg = load_config("local")
    out = cfg.data_dir / "outputs"
    all_reports = glob.glob(str(out / "*" / "openrewrite_loop_report.json"))
    held = [f for f in all_reports
            if any(h in Path(f).parent.name for h in args.holdout)]
    train = [f for f in all_reports if f not in held]

    print(f"[validate] training reports {len(train)}, held-out reports {len(held)} "
          f"({', '.join(args.holdout)})\n")
    if not held:
        print("[validate] no held-out reports found; run the loop on those repos first")
        return 1

    tl, hl = ledger_from(train), ledger_from(held)
    rows, agree, testable = [], 0, 0
    for key, tstat in sorted(tl.items()):
        tv = verdict(tstat)
        if tv == "too few runs":
            continue
        h = hl.get(key)
        if not h or not h["runs"]:
            rows.append({"smell": key[0], "refactoring": key[1], "training": tv,
                         "held_out": "not exercised", "agrees": None})
            continue
        testable += 1
        hmean = h["net"] / h["runs"]
        tmean = tstat["net"] / tstat["runs"]
        # agreement = same sign, i.e. the training verdict predicted the direction
        ok = (tmean < 0 and hmean < 0) or (tmean >= 0 and hmean >= 0)
        agree += ok
        rows.append({"smell": key[0], "refactoring": key[1], "training": tv,
                     "training_mean": round(tmean, 2), "held_out_runs": h["runs"],
                     "held_out_mean": round(hmean, 2), "agrees": ok})

    for r in rows:
        mark = "—" if r["agrees"] is None else ("agrees" if r["agrees"] else "DISAGREES")
        print(f"  {r['smell'][:26]:26s} {r['refactoring'][:19]:19s} "
              f"train={r['training'][:20]:20s} held={r.get('held_out_mean', '—')!s:>6s}  {mark}")

    print(f"\n[validate] {agree}/{testable} predictions held on unseen repositories"
          if testable else "\n[validate] no (smell, refactoring) pair was exercised on both sides")
    report = {"holdout": args.holdout, "training_reports": len(train),
              "holdout_reports": len(held), "testable_pairs": testable,
              "agreements": agree, "rows": rows,
              "training_ledger": summarise(tl), "holdout_ledger": summarise(hl)}
    dest = cfg.data_dir / "reports" / "ledger_validation.json"
    write_json(dest, report)
    print(f"[validate] report -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
