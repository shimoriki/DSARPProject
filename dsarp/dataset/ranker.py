"""Two models on the same data, answering two different questions.

**Baseline (ROSE-style classification).** Given a smell, which refactoring METHOD applies?
ROSE reports 96.9% accuracy / 95.2% F1 on exactly this, over 2M instances. It is the
published precedent and we reproduce its shape so the comparison is like-for-like.

**Ranker.** Given a smell and the N moves our pipeline has already proven *legal*, which one
should be applied? This is the question the system actually faces, and it is a different
question: our pdfbox run picked type-correct, legal moves and still added five smells.

Both are trained on real refactorings mined from real repositories. Neither sees whole
source files or detector output — features are structural facts computed from the code, per
the brief, so a model cannot memorise a project or learn Arcan's phrasing.

Held-out evaluation is BY REPOSITORY, never by random split: a random split lets the same
project appear in train and test, and a model that has seen a project's conventions is not
being tested on generalisation.
"""
from __future__ import annotations

import collections
import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------- features --

def _tokens(fqn: str) -> List[str]:
    """Identifier words in a name, lowercased — `TreeStatusPane` -> tree, status, pane."""
    out, cur = [], ""
    for ch in fqn.replace(".", " ").replace("_", " "):
        if ch.isupper() and cur and not cur[-1].isupper():
            out.append(cur); cur = ch
        elif ch == " ":
            if cur: out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur: out.append(cur)
    return [w.lower() for w in out if w]


def name_affinity(type_fqn: str, target_pkg: str) -> float:
    """How much a type's name already sounds like its destination package.

    Developers relocate `JsonConfigHelper` into `...serialization.config` far more often than
    into an unrelated package. It is a weak signal on its own and a useful one in a ranker.
    """
    a, b = set(_tokens(type_fqn.rsplit(".", 1)[-1])), set(_tokens(target_pkg))
    return len(a & b) / max(1, len(a | b))


def package_distance(from_pkg: str, to_pkg: str) -> int:
    """Segments that differ — a sibling move is 1, a move across the tree is larger."""
    a, b = from_pkg.split("."), to_pkg.split(".")
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return (len(a) - i) + (len(b) - i)


# Graph features are the ones that decide outcome. Measured on 8 pdfbox candidates with
# known outcomes, the name/depth/size features above had *identical* means for moves that
# reduced the smell and moves that increased it — they describe the move, and the outcome
# depends on the dependency structure the move acts on. Eight candidates that looked the
# same to those features ranged from -1 targeted/-3 collateral to +1/+2.
GRAPH_FEATURES = ["fan_in_from", "fan_out_from", "fan_in_to", "fan_out_to",
                  "edges_src_to_dst", "edges_dst_to_src", "would_close_cycle",
                  "type_refs_into_dst", "dst_refs_into_type"]

MOVE_FEATURES = ["name_affinity", "pkg_distance", "decl_lines", "n_signatures",
                 "is_test", "depth_from", "depth_to", "same_parent", "sig_annotations"]

FEATURES = MOVE_FEATURES + GRAPH_FEATURES


def graph_features(facts, graph, type_fqn: str, from_pkg: str, to_pkg: str) -> List[float]:
    """Structure around the move: degrees, the edges between the two packages, and whether
    the destination already depends on the source.

    `would_close_cycle` is the key one: moving a type INTO a package that already depends on
    its origin relocates the cycle edge instead of removing it. That is the failure mode
    behind every batched run that made things worse, and nothing in the old feature set
    could see it.
    """
    deg = {}
    if graph is not None:
        for n in getattr(graph, "nodes", []):
            m = n.metrics or {}
            deg[n.id] = (float(m.get("fan_in", 0) or 0), float(m.get("fan_out", 0) or 0))
    fi_f, fo_f = deg.get(from_pkg, (0.0, 0.0))
    fi_t, fo_t = deg.get(to_pkg, (0.0, 0.0))

    s2d = d2s = 0.0
    if graph is not None:
        for e in getattr(graph, "edges", []):
            if e.source == from_pkg and e.target == to_pkg:
                s2d += 1
            elif e.source == to_pkg and e.target == from_pkg:
                d2s += 1

    try:
        into_dst = float(len(facts.crossing_classes(from_pkg, to_pkg)))
        from_dst = float(len(facts.crossing_classes(to_pkg, from_pkg)))
    except Exception:
        into_dst = from_dst = 0.0
    text = ""
    try:
        text = facts.text_of(type_fqn) or ""
    except Exception:
        pass
    return [fi_f, fo_f, fi_t, fo_t, s2d, d2s,
            1.0 if d2s > 0 else 0.0,              # destination already depends on origin
            1.0 if to_pkg in text else 0.0,        # this type itself reaches into the target
            from_dst]


def features_for(type_fqn: str, from_pkg: str, to_pkg: str,
                 signatures: Optional[List[str]] = None,
                 decl_lines: int = 0, path: str = "") -> List[float]:
    sigs = signatures or []
    return [
        name_affinity(type_fqn, to_pkg),
        float(package_distance(from_pkg, to_pkg)),
        math.log1p(max(0, decl_lines)),
        math.log1p(len(sigs)),
        1.0 if "/test/" in path.replace("\\", "/") or type_fqn.endswith("Test") else 0.0,
        float(len(from_pkg.split("."))),
        float(len(to_pkg.split("."))),
        1.0 if from_pkg.rsplit(".", 1)[0] == to_pkg.rsplit(".", 1)[0] else 0.0,
        float(sum(1 for s in sigs if s.startswith("@"))),
    ]


# ------------------------------------------------------------------- data --

def load_examples(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for method, items in (data.get("examples") or {}).items():
        for e in items:
            e["method"] = method
            out.append(e)
    return out


def relocation_pairs(examples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Relocations where both sides name a type — the moves the pipeline can execute."""
    out = []
    for e in examples:
        if e["method"] not in ("Move Class", "Move And Rename Class"):
            continue
        b, a = e.get("before") or {}, e.get("after") or {}
        src, dst = b.get("element") or "", a.get("element") or ""
        if "." not in src or "." not in dst:
            continue
        out.append({
            "repo": e["repo"], "sha": e["sha"], "method": e["method"],
            "type": src, "from_pkg": src.rsplit(".", 1)[0],
            "to_pkg": dst.rsplit(".", 1)[0],
            "signatures": b.get("signatures") or [], "lines": b.get("lines") or 0,
            "path": b.get("path") or "",
        })
    return out


def build_ranking_groups(pairs: List[Dict[str, Any]], examples: List[Dict[str, Any]],
                         n_negatives: int = 5, seed: int = 0
                         ) -> List[Tuple[str, List[List[float]], List[int]]]:
    """One group per real move: the destination developers chose, plus alternatives.

    Negatives are other packages that genuinely exist in the same repository, so the model
    is choosing between real destinations rather than invented ones — the same question the
    pipeline's enumerator poses when it offers several legal targets for one finding.
    """
    rng = random.Random(seed)
    pkgs_by_repo: Dict[str, List[str]] = collections.defaultdict(set)
    for e in examples:
        for side in ("before", "after"):
            el = (e.get(side) or {}).get("element") or ""
            if "." in el:
                pkgs_by_repo[e["repo"]].add(el.rsplit(".", 1)[0])
    pkgs_by_repo = {k: sorted(v) for k, v in pkgs_by_repo.items()}

    groups = []
    for p in pairs:
        pool = [q for q in pkgs_by_repo.get(p["repo"], [])
                if q not in (p["to_pkg"], p["from_pkg"])]
        if len(pool) < 2:
            continue
        negs = rng.sample(pool, min(n_negatives, len(pool)))
        cands = [(p["to_pkg"], 1)] + [(c, 0) for c in negs]
        # Shuffle, or the gold answer sits at position 0 in every group and "always pick the
        # first candidate" scores a perfect 1.0 — which is what it did before this line, and
        # is the same position artefact that made three local models look like they were
        # selecting when they were not.
        rng.shuffle(cands)
        X = [features_for(p["type"], p["from_pkg"], c, p["signatures"], p["lines"], p["path"])
             for c, _ in cands]
        y = [lab for _, lab in cands]
        groups.append((p["repo"], X, y))
    return groups


# ----------------------------------------------------------------- models --

def repo_folds(repos: List[str], k: int = 4, seed: int = 0) -> List[List[str]]:
    """Split REPOSITORIES into folds. Never split examples — that leaks a project's style."""
    uniq = sorted(set(repos))
    random.Random(seed).shuffle(uniq)
    return [uniq[i::k] for i in range(k)]


def eval_classifier(examples: List[Dict[str, Any]], k: int = 4) -> Dict[str, Any]:
    """ROSE-shaped baseline: predict the refactoring METHOD from structural features."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import f1_score, accuracy_score

    rows, labels, repos = [], [], []
    for e in examples:
        b = e.get("before") or {}
        el = b.get("element") or ""
        if "." not in el:
            continue
        pkg = el.rsplit(".", 1)[0]
        rows.append(features_for(el, pkg, pkg, b.get("signatures"), b.get("lines") or 0,
                                 b.get("path") or ""))
        labels.append(e["method"]); repos.append(e["repo"])

    accs, f1s = [], []
    for fold in repo_folds(repos, k):
        tr = [i for i, r in enumerate(repos) if r not in fold]
        te = [i for i, r in enumerate(repos) if r in fold]
        if not te or len(set(labels[i] for i in tr)) < 2:
            continue
        m = RandomForestClassifier(n_estimators=200, random_state=0, class_weight="balanced")
        m.fit([rows[i] for i in tr], [labels[i] for i in tr])
        pred = m.predict([rows[i] for i in te])
        truth = [labels[i] for i in te]
        accs.append(accuracy_score(truth, pred))
        f1s.append(f1_score(truth, pred, average="weighted", zero_division=0))
    return {"task": "classification (which method)", "n": len(rows),
            "classes": len(set(labels)),
            "accuracy": round(sum(accs) / len(accs), 4) if accs else None,
            "f1_weighted": round(sum(f1s) / len(f1s), 4) if f1s else None,
            "folds": len(accs)}


def eval_ranker(groups: List[Tuple[str, List[List[float]], List[int]]], k: int = 4
                ) -> Dict[str, Any]:
    """Ranker: score candidate destinations, report precision@1 and MRR.

    Also reports the two baselines a ranker must beat to be worth anything: random choice,
    and always taking the first candidate offered — which is what every model we tested did
    on an unshuffled list.
    """
    from sklearn.ensemble import GradientBoostingClassifier

    repos = [g[0] for g in groups]
    p1, mrr, rnd, first = [], [], [], []
    for fold in repo_folds(repos, k):
        tr = [g for g in groups if g[0] not in fold]
        te = [g for g in groups if g[0] in fold]
        if not te or not tr:
            continue
        X = [x for _, Xs, _ in tr for x in Xs]
        y = [v for _, _, ys in tr for v in ys]
        if len(set(y)) < 2:
            continue
        m = GradientBoostingClassifier(random_state=0)
        m.fit(X, y)
        for _, Xs, ys in te:
            s = m.predict_proba(Xs)[:, 1]
            order = sorted(range(len(Xs)), key=lambda i: -s[i])
            gold = ys.index(1)
            rank = order.index(gold) + 1
            p1.append(1.0 if rank == 1 else 0.0)
            mrr.append(1.0 / rank)
            rnd.append(1.0 / len(Xs))
            first.append(1.0 if gold == 0 else 0.0)
    n = len(p1)
    avg = lambda v: round(sum(v) / len(v), 4) if v else None
    return {"task": "ranking (which destination)", "groups": n,
            "precision_at_1": avg(p1), "mrr": avg(mrr),
            "baseline_random_p@1": avg(rnd), "baseline_first_p@1": avg(first),
            "folds": k}
