"""Arms on paired targets: funnels, 4c with Wilson intervals, and exact McNemar.

Targets are the union of frozen components across arms, and a target an arm has no row for
counts as a failure there. McNemar is omitted below 20 targets: on fewer, a p-value says more
about the sample than about the arms.

    py -m dsarp.experiments.arm_compare <arm>=<rows.jsonl>[,<rows.jsonl>...] ...
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

MIN_TARGETS = 20


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre, half = p + z * z / (2 * n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    lo, hi = (centre - half) / (1 + z * z / n), (centre + half) / (1 + z * z / n)
    return max(0.0, round(lo, 4)), min(1.0, round(hi, 4))


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact binomial p-value on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def compare(rows_by_arm: Dict[str, List[Dict]]) -> Dict:
    key = lambda r: (r.get("repo", ""), tuple(r["component"]))
    by = {arm: {key(r): r for r in rows} for arm, rows in rows_by_arm.items()}
    targets = sorted(set().union(*(set(m) for m in by.values())))
    won = {arm: {t for t in targets if (m.get(t) or {}).get("level") == "4c"} for arm, m in by.items()}
    out = {"targets": len(targets), "arms": {}}
    for arm, m in by.items():
        levels: Dict[str, int] = {}
        for t in targets:
            lv = (m.get(t) or {}).get("level", "missing")
            levels[lv] = levels.get(lv, 0) + 1
        k = len(won[arm])
        out["arms"][arm] = {"levels": levels, "dissolved": k, "wilson_95": wilson(k, len(targets)),
                            "api_breaks": [(m[t].get("api") or {}).get("count") for t in targets
                                           if t in m and m[t].get("level") == "4c"]}
    arms = list(by)
    if len(targets) >= MIN_TARGETS:
        out["mcnemar"] = {"%s vs %s" % (a, b): mcnemar_exact(len(won[a] - won[b]), len(won[b] - won[a]))
                          for i, a in enumerate(arms) for b in arms[i + 1:]}
    return out


if __name__ == "__main__":
    rows = {}
    for spec in sys.argv[1:]:
        arm, paths = spec.split("=", 1)
        rows[arm] = []
        for p in paths.split(","):
            repo = Path(p).parent.name
            rows[arm] += [{"repo": repo, **json.loads(l)} for l in open(p, encoding="utf-8") if l.strip()]
    print(json.dumps(compare(rows), indent=1))
