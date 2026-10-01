"""Leaf-first ordering, after the Mikado Method.

Two ranking attempts have now failed here, in opposite ways:

  * detector severity (ATDI) is worse than useless -- trialling pdfbox candidates in ATDI
    order, the high-severity half produced 2/12 wins and a summed +12 smells, the low half
    6/13 and -273;
  * a regressor trained on 94 measured outcomes captures 0.783 of oracle on pdfbox, 0.25 on
    log4j2 and -0.786 on tika, where it picks actively harmful candidates.

The Mikado Method offers a third idea and, unlike the other two, an explanation for why the
first one failed. It maps refactoring dependencies as a tree and works from the LEAVES inward:
you cannot take the last stick until the others are gone. A large architectural smell is a
ROOT -- it is large precisely because much depends on it -- so ordering by severity attacks
the one thing that cannot move yet. That is exactly the +12 / -273 split.

So: order candidates by how little the rest of the smelly subgraph depends on them.

This is a heuristic with practitioner provenance rather than a learned model, and it is
evaluated the same strict way everything else here is: against the measured outcomes, held out
by repository, scored in smells actually removed.

STATUS: disproved. Leaf-first ordering scored -0.115 against the oracle. Kept as a
recorded negative result. No caller by design -- see docs/negative-results.md.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def smelly_packages(findings: List[Dict[str, Any]]) -> set:
    """Every package named by a cyclic-dependency finding."""
    out = set()
    for f in findings:
        if "Cyclic" not in (f.get("smell_type") or ""):
            continue
        for c in (f.get("components") or []):
            c = c.strip()
            if c:
                out.add(c)
    return out


def leaf_depth(graph, packages: set) -> Dict[str, float]:
    """How much of the smelly subgraph depends on each package.

    A leaf has few dependents WITHIN the tangle: removing it frees nothing else, so it can be
    taken now. A root has many, and is unreachable until they are gone. Dependencies outside
    the tangle are ignored deliberately -- a package can be heavily used by healthy code and
    still be a leaf of the cycle, which is the case worth acting on.
    """
    depth = {p: 0.0 for p in packages}
    if graph is None:
        return depth
    for e in getattr(graph, "edges", []):
        src, dst = getattr(e, "source", None), getattr(e, "target", None)
        if src in packages and dst in packages and src != dst:
            depth[dst] = depth.get(dst, 0.0) + 1.0
    return depth


def order(candidates: List[Dict[str, Any]], graph, findings: List[Dict[str, Any]]
          ) -> List[Tuple[Dict[str, Any], float]]:
    """Candidates leaf-first: fewest dependents inside the tangle, first.

    The package scored is the one the refactoring acts ON -- the implementation's package for
    an inversion, the type's own package for a move. Ties keep enumeration order, which is
    stable across runs.
    """
    pkgs = smelly_packages(findings)
    depth = leaf_depth(graph, pkgs)
    scored = []
    for c in candidates:
        fqn = c.get("type") or ""
        pkg = fqn.rsplit(".", 1)[0] if "." in fqn else ""
        scored.append((c, depth.get(pkg, 0.0)))
    return sorted(scored, key=lambda p: p[1])


def evaluate_retrospectively(rows: List[Dict[str, Any]],
                             depth_by_pkg: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
    """Would leaf-first ordering have picked better candidates than we did?

    Uses outcomes already measured, so it costs no builds. For each repository, take the k
    lowest-depth candidates and sum the smells they actually removed, against the oracle
    (best possible k) and the expectation of a random pick.
    """
    per_repo: Dict[str, Any] = {}
    tot_model = tot_oracle = tot_random = 0.0
    by_repo: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_repo.setdefault(r["project"], []).append(r)

    for repo, rs in sorted(by_repo.items()):
        removed = []
        for r in rs:
            if not r.get("compiled"):
                removed.append(0.0)
                continue
            b, a = r.get("total_before"), r.get("total_after")
            removed.append(float(b - a) if b is not None and a is not None else 0.0)
        depths = depth_by_pkg.get(repo) or {}
        keys = []
        for r in rs:
            fqn = r.get("type") or ""
            keys.append(depths.get(fqn.rsplit(".", 1)[0] if "." in fqn else "", 0.0))
        if len(rs) < 3:
            continue
        k = max(1, len(rs) // 3)
        pick = sorted(range(len(rs)), key=lambda i: keys[i])[:k]
        model = sum(removed[i] for i in pick)
        oracle = sum(sorted(removed, reverse=True)[:k])
        rand = (sum(removed) / len(removed)) * k
        per_repo[repo] = {"n": len(rs), "k": k, "model": round(model, 1),
                          "oracle": round(oracle, 1), "random_expected": round(rand, 1),
                          "captured": (round(model / oracle, 3) if oracle > 0 else None)}
        tot_model += model
        tot_oracle += oracle
        tot_random += rand
    return {"per_repo": per_repo,
            "smells_removed_at_k": {"model": round(tot_model, 1),
                                    "oracle": round(tot_oracle, 1),
                                    "random_expected": round(tot_random, 1)},
            "fraction_of_oracle": (round(tot_model / tot_oracle, 3) if tot_oracle > 0 else None),
            "beats_random": tot_model > tot_random}
