"""Train the grokking-style neural ranker, compare to GBM (LORO), deploy the winner.

Produces:
  data/models/grokking_curve.json   — train vs held-out-repo accuracy per epoch
  data/models/neural_loro.json       — neural leave-one-repository-out
  data/models/ranker.pkl             — REDEPLOYED only if neural beats the GBM on LORO
  data/models/model_comparison.json  — GBM vs neural summary

Usage: python scripts/train_neural_ranker.py [--epochs 3000] [--hidden 64,32] [--wd 0.01] [--deploy]
"""
from __future__ import annotations

import argparse
import pickle
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401
from dsarp.config import load_config
from dsarp.features.extractor import FEATURE_SCHEMA_VERSION
from dsarp.training.neural_ranker import train_grokking_mlp, loro_neural
from dsarp.util import read_json, read_jsonl, write_json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="data/training/real_labeled_candidates.jsonl")
    ap.add_argument("--epochs", type=int, default=3000)
    ap.add_argument("--hidden", default="64,32")
    ap.add_argument("--wd", type=float, default=1e-2, help="weight decay (the grokking knob)")
    ap.add_argument("--curve-holdout", default="apache-commons-io")
    ap.add_argument("--deploy", action="store_true", help="deploy neural only if it wins on LORO")
    args = ap.parse_args()

    cfg = load_config("local")
    hidden = tuple(int(x) for x in args.hidden.split(","))
    rows = list(read_jsonl(Path(args.dataset)))
    repos = sorted(set(r.get("project_id", "?") for r in rows))
    print(f"[neural] {len(rows)} rows, {len(repos)} repos, hidden={hidden}, wd={args.wd}, epochs={args.epochs}")

    # 1) single held-out run -> grokking curve
    holdout = args.curve_holdout if args.curve_holdout in repos else repos[0]
    _, rep = train_grokking_mlp(rows, val_repo=holdout, hidden=hidden,
                                epochs=args.epochs, weight_decay=args.wd)
    write_json(cfg.data_dir / "models" / "grokking_curve.json", {
        "held_out_repo": holdout, "hidden": rep.hidden, "weight_decay": rep.weight_decay,
        "epochs": rep.epochs, "best_val_acc": rep.best_val_acc, "best_epoch": rep.best_epoch,
        "final_train_acc": rep.final_train_acc, "grokking_gap_epochs": rep.grokking_gap_epochs,
        "grokking_detected": rep.grokking_detected, "curve": rep.curve})
    print(f"[neural] curve (held out {holdout}): final_train_acc={rep.final_train_acc} "
          f"best_val_acc={rep.best_val_acc}@ep{rep.best_epoch} "
          f"grokking_gap={rep.grokking_gap_epochs}ep detected={rep.grokking_detected}")

    # 2) neural LORO
    nl = loro_neural(rows, hidden=hidden, epochs=min(args.epochs, 1500), weight_decay=args.wd)
    write_json(cfg.data_dir / "models" / "neural_loro.json", nl)
    print(f"[neural] neural LORO mean={nl['mean_validation_score']}")

    # 3) compare to GBM
    gbm = read_json(cfg.data_dir / "models" / "loro_report.json", default={}) or {}
    gbm_score = gbm.get("mean_validation_score", 0.0)
    winner = "neural" if nl["mean_validation_score"] > gbm_score else "gbm"
    comparison = {"gbm_loro": gbm_score, "neural_loro": nl["mean_validation_score"],
                  "winner": winner, "hidden": list(hidden), "weight_decay": args.wd,
                  "created_at": datetime.now(timezone.utc).isoformat()}
    write_json(cfg.data_dir / "models" / "model_comparison.json", comparison)
    print(f"[neural] COMPARE  gbm_loro={gbm_score}  neural_loro={nl['mean_validation_score']}  "
          f"=> winner={winner}")

    # 4) deploy the winner (neural: retrain on all repos, checkpoint on one small held-out)
    if args.deploy and winner == "neural":
        model, frep = train_grokking_mlp(rows, val_repo=repos[0], hidden=hidden,
                                         epochs=args.epochs, weight_decay=args.wd)
        meta = {"ranker_version": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
                "backend": "neural-mlp-grokking", "training_repositories": repos,
                "excluded_repositories": ["apache-cassandra"],
                "feature_schema_version": FEATURE_SCHEMA_VERSION,
                "training_example_count": len(rows), "validation_strategy": "leave-one-repository-out",
                "validation_score": nl["mean_validation_score"], "hidden": list(hidden),
                "weight_decay": args.wd, "grokking_gap_epochs": frep.grokking_gap_epochs,
                "created_at": datetime.now(timezone.utc).isoformat()}
        with open(cfg.data_dir / "models" / "ranker.pkl", "wb") as fh:
            pickle.dump({"model": model, "metadata": meta}, fh)
        write_json(cfg.data_dir / "models" / "ranker_report.json",
                   {"metadata": meta, "feature_importance": {}})
        print(f"[neural] DEPLOYED neural ranker ({nl['mean_validation_score']} LORO)")
    elif args.deploy:
        print(f"[neural] KEEPING GBM (LORO {gbm_score} >= neural {nl['mean_validation_score']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
