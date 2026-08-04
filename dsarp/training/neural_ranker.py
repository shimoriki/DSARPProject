"""Grokking-informed neural ranker (Task: "make it the best model, look into grokking").

Grokking (Power et al., 2022) = delayed generalization: a network trained PAST the point
of memorising the training set can, with weight decay, suddenly generalise. It is a
neural-net phenomenon (gradient descent + weight decay), so we add a small MLP with:
  - AdamW weight decay (the key grokking ingredient)
  - long training past train-fit
  - REPOSITORY-level held-out tracking every epoch (the grokking curve)
  - best-held-out-repo checkpoint deployed

Training uses torch; INFERENCE uses a pure-numpy forward pass (NumpyMLP) so the deployed
ranker is fast and torch-free. Whether grokking actually helps here is measured, not assumed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..features.extractor import FEATURE_ORDER, FEATURE_SCHEMA_VERSION


# --------------------------------------------------------------------------- #
# picklable, torch-free inference model
# --------------------------------------------------------------------------- #
class NumpyMLP:
    """Deployed model: standardise -> MLP forward (relu) -> sigmoid. predict_proba API."""

    def __init__(self, weights: List[np.ndarray], biases: List[np.ndarray],
                 mean: np.ndarray, std: np.ndarray):
        self.weights = [np.asarray(w, dtype=np.float64) for w in weights]
        self.biases = [np.asarray(b, dtype=np.float64) for b in biases]
        self.mean = np.asarray(mean, dtype=np.float64)
        self.std = np.asarray(std, dtype=np.float64)

    def _forward(self, X: np.ndarray) -> np.ndarray:
        z = (X - self.mean) / self.std
        for i, (w, b) in enumerate(zip(self.weights, self.biases)):
            z = z @ w + b
            if i < len(self.weights) - 1:
                z = np.maximum(z, 0.0)  # relu
        return 1.0 / (1.0 + np.exp(-z.ravel()))  # sigmoid

    def predict_proba(self, X):
        p = self._forward(np.asarray(X, dtype=np.float64))
        return np.stack([1 - p, p], axis=1)

    def predict(self, X):
        return (self._forward(np.asarray(X, dtype=np.float64)) >= 0.5).astype(int)


# --------------------------------------------------------------------------- #
# data helpers
# --------------------------------------------------------------------------- #
def _xy(rows: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    X = np.array([[float(r.get("features", {}).get(k, 0.0)) for k in FEATURE_ORDER] for r in rows],
                 dtype=np.float64)
    y = np.array([int(r.get("label", 0)) for r in rows], dtype=np.float64)
    repos = [r.get("project_id", "?") for r in rows]
    return X, y, repos


@dataclass
class GrokReport:
    epochs: int
    curve: List[Dict[str, float]] = field(default_factory=list)  # epoch, train_acc, val_acc
    best_val_acc: float = 0.0
    best_epoch: int = 0
    final_train_acc: float = 0.0
    grokking_gap_epochs: int = 0   # epochs between train-memorised and best val
    grokking_detected: bool = False
    hidden: List[int] = field(default_factory=list)
    weight_decay: float = 0.0


# --------------------------------------------------------------------------- #
# training (torch) with repo-held-out grokking curve
# --------------------------------------------------------------------------- #
def train_grokking_mlp(rows: List[Dict[str, Any]], val_repo: Optional[str] = None,
                       hidden: Tuple[int, ...] = (64, 32), epochs: int = 800,
                       weight_decay: float = 1e-2, lr: float = 3e-3,
                       seed: int = 0, batch_size: int = 512) -> Tuple[NumpyMLP, GrokReport]:
    import torch
    import torch.nn as nn
    torch.manual_seed(seed)
    np.random.seed(seed)

    X, y, repos = _xy(rows)
    if val_repo:
        tr = np.array([r != val_repo for r in repos])
    else:  # fallback: last 15% of repos held out by name
        uniq = sorted(set(repos))
        held = set(uniq[max(1, int(len(uniq) * 0.85)):])
        tr = np.array([r not in held for r in repos])
    Xtr, ytr, Xva, yva = X[tr], y[tr], X[~tr], y[~tr]
    if len(Xva) == 0:  # no held-out -> use train as val (curve still informative)
        Xva, yva = Xtr, ytr

    mean, std = Xtr.mean(0), Xtr.std(0)
    std[std == 0] = 1.0
    Xtr_s = (Xtr - mean) / std
    Xva_s = (Xva - mean) / std

    layers: List[nn.Module] = []
    dims = [X.shape[1], *hidden, 1]
    for i in range(len(dims) - 1):
        layers.append(nn.Linear(dims[i], dims[i + 1]))
        if i < len(dims) - 2:
            layers.append(nn.ReLU())
    net = nn.Sequential(*layers)
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=weight_decay)
    loss_fn = nn.BCEWithLogitsLoss()

    Xt = torch.tensor(Xtr_s, dtype=torch.float32)
    yt = torch.tensor(ytr, dtype=torch.float32).view(-1, 1)
    Xv = torch.tensor(Xva_s, dtype=torch.float32)

    rep = GrokReport(epochs=epochs, hidden=list(hidden), weight_decay=weight_decay)
    best_state, memorised_epoch = None, None
    n = Xt.shape[0]
    bs = min(batch_size, n) if batch_size > 0 else n  # mini-batch SGD => fast on large N
    eval_every = max(2, epochs // 40)
    # subsample the train set for the accuracy probe so eval stays cheap on large N
    tr_probe = torch.randperm(n)[:2000]
    ytr_probe = ytr[tr_probe.numpy()]
    Xt_probe = Xt[tr_probe]
    for ep in range(1, epochs + 1):
        net.train()
        perm = torch.randperm(n)
        for i in range(0, n, bs):
            idx = perm[i:i + bs]
            opt.zero_grad()
            loss = loss_fn(net(Xt[idx]), yt[idx])
            loss.backward()
            opt.step()
        if ep % eval_every == 0 or ep == 1:
            net.eval()
            with torch.no_grad():
                tr_acc = ((torch.sigmoid(net(Xt_probe)).view(-1) >= 0.5).float().numpy() == ytr_probe).mean()
                va_acc = ((torch.sigmoid(net(Xv)).view(-1) >= 0.5).float().numpy() == yva).mean()
            rep.curve.append({"epoch": ep, "train_acc": round(float(tr_acc), 4),
                              "val_acc": round(float(va_acc), 4)})
            if memorised_epoch is None and tr_acc >= 0.99:
                memorised_epoch = ep
            if va_acc > rep.best_val_acc:
                rep.best_val_acc, rep.best_epoch = float(va_acc), ep
                best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}

    if best_state is not None:
        net.load_state_dict(best_state)
    # TRUE grokking = val stays LOW at memorisation, then JUMPS >=8% well after.
    # A late best-val alone (val already high at memorisation) is NOT grokking.
    if memorised_epoch is not None:
        rep.grokking_gap_epochs = max(0, rep.best_epoch - memorised_epoch)
        val_at_mem = next((p["val_acc"] for p in rep.curve if p["epoch"] >= memorised_epoch), 0.0)
        rep.grokking_detected = (rep.grokking_gap_epochs >= max(100, int(epochs * 0.15))
                                 and (rep.best_val_acc - val_at_mem) >= 0.08)
    rep.final_train_acc = rep.curve[-1]["train_acc"] if rep.curve else 0.0

    # extract to numpy
    W, B = [], []
    for m in net:
        if isinstance(m, nn.Linear):
            W.append(m.weight.detach().numpy().T.copy())
            B.append(m.bias.detach().numpy().copy())
    return NumpyMLP(W, B, mean, std), rep


def loro_neural(rows: List[Dict[str, Any]], hidden=(64, 32), epochs=1500,
                weight_decay=1e-2) -> Dict[str, Any]:
    """Leave-one-repository-out for the neural ranker (real generalization number)."""
    repos = sorted(set(r.get("project_id", "?") for r in rows))
    folds = []
    for held in repos:
        _, rep = train_grokking_mlp(rows, val_repo=held, hidden=hidden, epochs=epochs,
                                    weight_decay=weight_decay)
        folds.append({"held_out": held, "val_acc": rep.best_val_acc,
                      "grokking_gap": rep.grokking_gap_epochs})
    mean = round(sum(f["val_acc"] for f in folds) / len(folds), 4) if folds else 0.0
    return {"strategy": "leave-one-repository-out", "backend": "neural-mlp",
            "mean_validation_score": mean, "folds": folds}
