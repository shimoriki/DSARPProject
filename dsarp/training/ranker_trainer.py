"""Task 9 / addendum §8 — multi-repository ranker training.

- repository-level train/validation split (never shuffle rows within a repo)
- optional leave-one-repository-out validation
- backend: LightGBM -> sklearn GradientBoosting/RandomForest -> deterministic fallback
- feature importance export, overfitting warning, versioned metadata
- Cassandra/unseen leakage blocked via SplitManager before any fit.
"""
from __future__ import annotations

import csv
import math
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..features.extractor import FEATURE_ORDER, FEATURE_SCHEMA_VERSION
from ..splits.manager import SplitManager
from ..util import read_jsonl, write_json


class _WeightModel:
    """Deterministic fallback aligned to FEATURE_ORDER (used when no fit possible)."""
    def __init__(self, weights: List[float]):
        self.weights = weights

    def predict_proba(self, X):
        out = []
        for row in X:
            s = sum(w * x for w, x in zip(self.weights, row))
            p = 1 / (1 + math.exp(-0.5 * s))
            out.append([1 - p, p])
        return out


def _default_weights() -> List[float]:
    w = {k: 0.0 for k in FEATURE_ORDER}
    w.update({"graph_delta": 1.2, "estimated_edges_removed": 0.6, "severity": 0.5,
              "catalogue_rank": 0.5, "tool_agreement_count": 0.2, "edge_confidence": 0.3,
              "risk": -0.8, "public_api_risk": -0.5})
    return [w[k] for k in FEATURE_ORDER]


def _rows_to_xy(rows: List[Dict[str, Any]]) -> Tuple[List[List[float]], List[int]]:
    X, y = [], []
    for r in rows:
        feats = r.get("features", {})
        X.append([float(feats.get(k, 0.0)) for k in FEATURE_ORDER])
        y.append(int(r.get("label", 0)))
    return X, y


def _fit_backend(X, y):
    """Return (model, backend_name). None model if not fittable."""
    if not X or len(set(y)) < 2:
        return None, "fallback"
    try:
        import lightgbm as lgb
        m = lgb.LGBMClassifier(n_estimators=200, max_depth=4, verbose=-1)
        m.fit(X, y)
        return m, "lightgbm"
    except Exception:
        pass
    try:
        from sklearn.ensemble import GradientBoostingClassifier
        m = GradientBoostingClassifier(n_estimators=150, max_depth=3)
        m.fit(X, y)
        return m, "sklearn.GradientBoosting"
    except Exception:
        pass
    try:
        from sklearn.ensemble import RandomForestClassifier
        m = RandomForestClassifier(n_estimators=200, max_depth=6)
        m.fit(X, y)
        return m, "sklearn.RandomForest"
    except Exception:
        return None, "fallback"


def _score(model, X, y) -> float:
    if not X:
        return 0.0
    try:
        preds = [p[-1] for p in model.predict_proba(X)]
    except Exception:
        return 0.0
    # accuracy at 0.5 threshold
    correct = sum(1 for p, t in zip(preds, y) if int(p >= 0.5) == t)
    return round(correct / len(y), 4)


def _importance(model) -> Dict[str, float]:
    imp = None
    if hasattr(model, "feature_importances_"):
        imp = list(model.feature_importances_)
    elif hasattr(model, "coef_"):
        imp = list(abs(c) for c in model.coef_[0])
    elif isinstance(model, _WeightModel):
        imp = [abs(w) for w in model.weights]
    if imp is None:
        return {}
    total = sum(imp) or 1.0
    return {k: round(v / total, 4) for k, v in zip(FEATURE_ORDER, imp)}


class RankerTrainer:
    def __init__(self, out_dir: Path):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.splits = SplitManager()

    def _load_rows(self, dataset: Path) -> List[Dict[str, Any]]:
        rows = list(read_jsonl(dataset))
        # hard leakage guard: drop any row from a non-trainable repo
        clean = [r for r in rows if self.splits.is_training_allowed(r.get("project_id", ""))]
        return clean

    def train(self, dataset: Path, validation_repo: Optional[str] = None,
              persist: bool = True) -> Dict[str, Any]:
        rows = self._load_rows(dataset)
        repos = sorted({r.get("project_id", "unknown") for r in rows})
        if validation_repo:
            train_rows = [r for r in rows if r.get("project_id") != validation_repo]
            val_rows = [r for r in rows if r.get("project_id") == validation_repo]
        else:
            train_rows, val_rows = rows, []
        Xtr, ytr = _rows_to_xy(train_rows)
        model, backend = _fit_backend(Xtr, ytr)
        if model is None:
            model, backend = _WeightModel(_default_weights()), "fallback"
        train_score = _score(model, Xtr, ytr) if Xtr else 0.0
        val_score = _score(model, *_rows_to_xy(val_rows)) if val_rows else None
        overfit = bool(val_score is not None and (train_score - val_score) > 0.25)

        metadata = {
            "ranker_version": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
            "backend": backend,
            "training_repositories": [r for r in repos if r != validation_repo],
            "excluded_repositories": self.splits.unseen,
            "validation_repository": validation_repo,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "training_example_count": len(train_rows),
            "validation_example_count": len(val_rows),
            "validation_strategy": "leave-one-repository-out" if validation_repo else "all-train",
            "train_score": train_score, "validation_score": val_score,
            "overfitting_warning": overfit,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        importance = _importance(model)

        # persist only the production model (full-data train), never per-fold LORO models
        if persist:
            with open(self.out_dir / "ranker.pkl", "wb") as fh:
                pickle.dump({"model": model, "metadata": metadata}, fh)
            write_json(self.out_dir / "ranker_report.json",
                       {"metadata": metadata, "feature_importance": importance})
            with open(self.out_dir / "feature_importance.csv", "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["feature", "importance"])
                for k, v in sorted(importance.items(), key=lambda kv: -kv[1]):
                    w.writerow([k, v])
        return {"metadata": metadata, "feature_importance": importance,
                "model_path": str(self.out_dir / "ranker.pkl")}

    def leave_one_repo_out(self, dataset: Path) -> Dict[str, Any]:
        rows = self._load_rows(dataset)
        repos = sorted({r.get("project_id", "unknown") for r in rows})
        folds = []
        for held in repos:
            res = self.train(dataset, validation_repo=held, persist=False)  # never clobber prod model
            m = res["metadata"]
            folds.append({"held_out": held, "train_count": m["training_example_count"],
                          "val_count": m["validation_example_count"],
                          "train_score": m["train_score"], "validation_score": m["validation_score"],
                          "overfitting_warning": m["overfitting_warning"]})
        report = {"strategy": "leave-one-repository-out", "folds": folds,
                  "mean_validation_score": round(
                      sum(f["validation_score"] or 0 for f in folds) / len(folds), 4) if folds else 0.0}
        write_json(self.out_dir / "loro_report.json", report)
        return report


def train_ranker_from_dataset(out_dir: Path, dataset: Path,
                              validation_repo: Optional[str] = None) -> Dict[str, Any]:
    return RankerTrainer(out_dir).train(dataset, validation_repo)
