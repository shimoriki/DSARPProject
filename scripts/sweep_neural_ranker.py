"""Sweep MLP capacity x weight-decay (the grokking knob), deploy the best on LORO.

Small, honest hyperparameter search over repository-level generalization. Deploys the
best config only if it beats the current GBM baseline. Fast (numpy inference, tiny nets).
"""
from __future__ import annotations

import pickle
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401
from dsarp.config import load_config
from dsarp.features.extractor import FEATURE_SCHEMA_VERSION
from dsarp.training.neural_ranker import loro_neural, train_grokking_mlp
from dsarp.util import read_json, read_jsonl, write_json

# (hidden, weight_decay) — includes a small and a LARGER model, low/high weight decay
CONFIGS = [
    ((64, 32), 0.01),
    ((64, 32), 0.1),      # stronger weight decay (grokking-relevant)
    ((128, 64), 0.01),    # larger model
    ((128, 64, 32), 0.03),  # larger + deeper
]


def main() -> int:
    cfg = load_config("local")
    rows = list(read_jsonl(cfg.data_dir / "training" / "real_labeled_candidates.jsonl"))
    repos = sorted(set(r.get("project_id", "?") for r in rows))
    gbm = (read_json(cfg.data_dir / "models" / "loro_report.json", default={}) or {}).get(
        "mean_validation_score", 0.0)
    print(f"[sweep] {len(rows)} rows, {len(repos)} repos | GBM LORO baseline = {gbm}")

    results = []
    for hidden, wd in CONFIGS:
        nl = loro_neural(rows, hidden=hidden, epochs=1500, weight_decay=wd)
        results.append({"hidden": list(hidden), "weight_decay": wd,
                        "loro": nl["mean_validation_score"]})
        print(f"[sweep] hidden={hidden} wd={wd} -> LORO {nl['mean_validation_score']}")

    results.sort(key=lambda r: -r["loro"])
    best = results[0]
    write_json(cfg.data_dir / "models" / "neural_sweep.json",
               {"gbm_loro": gbm, "results": results, "best": best})
    print(f"[sweep] BEST: hidden={best['hidden']} wd={best['weight_decay']} LORO={best['loro']} "
          f"(GBM {gbm})")

    if best["loro"] > gbm:
        hidden = tuple(best["hidden"])
        model, frep = train_grokking_mlp(rows, val_repo=repos[0], hidden=hidden,
                                         epochs=3000, weight_decay=best["weight_decay"])
        meta = {"ranker_version": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
                "backend": "neural-mlp-grokking", "training_repositories": repos,
                "excluded_repositories": ["apache-cassandra"],
                "feature_schema_version": FEATURE_SCHEMA_VERSION,
                "training_example_count": len(rows), "validation_strategy": "leave-one-repository-out",
                "validation_score": best["loro"], "hidden": best["hidden"],
                "weight_decay": best["weight_decay"], "grokking_gap_epochs": frep.grokking_gap_epochs,
                "grokking_detected": frep.grokking_detected,
                "created_at": datetime.now(timezone.utc).isoformat()}
        with open(cfg.data_dir / "models" / "ranker.pkl", "wb") as fh:
            pickle.dump({"model": model, "metadata": meta}, fh)
        write_json(cfg.data_dir / "models" / "ranker_report.json",
                   {"metadata": meta, "feature_importance": {}})
        print(f"[sweep] DEPLOYED best neural ranker (LORO {best['loro']})")
    else:
        print("[sweep] GBM still best; keeping it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
