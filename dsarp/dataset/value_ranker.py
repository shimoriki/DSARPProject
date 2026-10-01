"""Rank refactoring candidates by EXPECTED SMELLS REMOVED, learned from measured outcomes.

Every ranking this project has used was a proxy. ATDI severity is the detector's opinion of how
bad a smell is, and it is measurably anti-predictive here: trialling pdfbox candidates in ATDI
order, the high-severity half produced 2/12 wins and a summed +12 smells, the low half 6/13 and
-273. A hand-read graph heuristic (`fan_out_from`) separated outcomes on the eight candidates it
was derived from and predicted nothing on two unseen repositories.

This ranks by the quantity that actually matters, for one reason the data makes unavoidable:

    value is concentrated, not spread.
    MissingOperandException alone removed 240 of the 289 smells ever removed here.

A hit-rate objective treats that move and a -1 move as equally good. An expected-value objective
does not. So the target is the signed change in TOTAL smells, regressed rather than classified,
and candidates are ordered by predicted reduction.

Held out BY REPOSITORY, always — a random split lets a model learn one project's package
conventions and call it generalisation.

STATUS: disproved. Ranking by expected smells removed inherits the smell-count
metric that a bytecode cycle oracle later showed measures participation in a few
giant components. Kept as a recorded negative result. No caller by design -- see
docs/negative-results.md.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .ranker import FEATURES, GRAPH_FEATURES, MOVE_FEATURES

# The operation is part of the candidate, and the two behave differently enough to matter:
# relocation nets 17% across 72 candidates, inversion 36% across 14.
OP_FEATURES = ["op_move", "op_extract", "op_invert", "classes_inverted"]
ALL_FEATURES = FEATURES + OP_FEATURES


def _op_block(row: Dict[str, Any]) -> List[float]:
    op = row.get("op") or "moveClass"
    return [
        1.0 if op == "moveClass" else 0.0,
        1.0 if op == "extractInterface" else 0.0,
        1.0 if op == "invertEdge" else 0.0,
        float(row.get("classes_inverted") or 1),
    ]


def load_rows(labels_dir: Path) -> List[Dict[str, Any]]:
    """Every labelled candidate, from both the move corpus and the inversion corpus."""
    out: List[Dict[str, Any]] = []
    for pattern in ("labels/*/labels.json", "dip/*/labels.json"):
        for f in sorted(Path(labels_dir).glob(pattern)):
            for r in json.loads(f.read_text(encoding="utf-8")):
                r.setdefault("op", "moveClass")
                out.append(r)
    return out


def target(row: Dict[str, Any]) -> Optional[float]:
    """Smells removed: positive is good, zero when the build failed.

    A candidate that does not compile removed nothing — it is not missing data, it is a
    measured zero, and dropping those rows would train the model only on candidates that
    already worked.
    """
    if not row.get("compiled"):
        return 0.0
    b, a = row.get("total_before"), row.get("total_after")
    if b is None or a is None:
        return None
    return float(b - a)


def featurise(rows: List[Dict[str, Any]]) -> Tuple[List[List[float]], List[float], List[str]]:
    X, y, repos = [], [], []
    for r in rows:
        t = target(r)
        f = r.get("features")
        if t is None or not f:
            continue
        # Older rows carry 18 features, newer ones the same 18; pad defensively so a schema
        # drift shows up as a shape error here rather than as a silently worse model.
        if len(f) != len(FEATURES):
            continue
        X.append(list(f) + _op_block(r))
        y.append(t)
        repos.append(r["project"])
    return X, y, repos


def evaluate(labels_dir: Path = Path("data/outputs")) -> Dict[str, Any]:
    """Leave-one-repository-out, scored the way the system would actually be used.

    Accuracy is the wrong score for a ranker. What matters is: if we apply the model's top-k
    picks, how many smells do we remove, against picking k at random or by the detector's own
    severity order? That is reported as `smells_removed_at_k`.
    """
    from sklearn.ensemble import GradientBoostingRegressor

    rows = load_rows(labels_dir)
    X, y, repos = featurise(rows)
    uniq = sorted(set(repos))
    result: Dict[str, Any] = {"n": len(X), "repos": uniq,
                              "total_smells_removed": sum(v for v in y if v > 0)}
    if len(uniq) < 2 or len(X) < 12:
        result["status"] = "insufficient data for leave-one-repo-out"
        return result

    per_repo, gains = {}, []
    for held in uniq:
        tr = [i for i, r in enumerate(repos) if r != held]
        te = [i for i, r in enumerate(repos) if r == held]
        if not te or len(tr) < 8:
            continue
        m = GradientBoostingRegressor(random_state=0, n_estimators=200, max_depth=2,
                                      learning_rate=0.05)
        m.fit([X[i] for i in tr], [y[i] for i in tr])
        pred = m.predict([X[i] for i in te])
        actual = [y[i] for i in te]
        k = max(1, len(te) // 3)
        order = sorted(range(len(te)), key=lambda i: -pred[i])
        model_k = sum(actual[i] for i in order[:k])
        best_k = sum(sorted(actual, reverse=True)[:k])
        mean_k = (sum(actual) / len(actual)) * k          # expectation of a random pick
        per_repo[held] = {"n": len(te), "k": k,
                          "model": round(model_k, 1), "oracle": round(best_k, 1),
                          "random_expected": round(mean_k, 1),
                          "captured": (round(model_k / best_k, 3) if best_k > 0 else None)}
        gains.append((model_k, best_k, mean_k))
    if gains:
        mk = sum(g[0] for g in gains); bk = sum(g[1] for g in gains)
        rk = sum(g[2] for g in gains)
        result.update(status="evaluated", per_repo=per_repo,
                      smells_removed_at_k={"model": round(mk, 1), "oracle": round(bk, 1),
                                           "random_expected": round(rk, 1)},
                      fraction_of_oracle=(round(mk / bk, 3) if bk > 0 else None),
                      beats_random=(mk > rk))
    else:
        result["status"] = "no usable folds"
    return result


def fit(labels_dir: Path = Path("data/outputs")):
    """Train on everything, for ranking live candidates."""
    from sklearn.ensemble import GradientBoostingRegressor
    rows = load_rows(labels_dir)
    X, y, _ = featurise(rows)
    m = GradientBoostingRegressor(random_state=0, n_estimators=200, max_depth=2,
                                  learning_rate=0.05)
    m.fit(X, y)
    return m


def rank(model, candidates: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], float]]:
    """Candidates ordered by predicted smells removed, best first."""
    feats = [list(c["features"]) + _op_block(c) for c in candidates]
    scores = model.predict(feats)
    return sorted(zip(candidates, scores), key=lambda p: -p[1])
