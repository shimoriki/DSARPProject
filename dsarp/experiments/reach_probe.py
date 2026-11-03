"""Phase 1 of the mixed-operator study: does adding inversions reach more whole cycles?

For each SCC of at most four packages, plan with moves alone and with moves and inversions,
and count a plan as dissolvable only when the arithmetic leaves no package cycling AND Spoon
accepts it on a copy. No tests run: this measures reach, not acceptance. The stop rule was
fixed in the spec before any probe ran: continue only if the mix makes at least 10 more
Arcan-reported SCCs dissolvable than moves alone, across Discovery.

    py -m dsarp.experiments.reach_probe <repos.txt> <out>

Each line of repos.txt is `<repo> [<existing scc_dissolve out dir>]`; an existing directory
reuses its compiled baseline tree and cached baseline. Holdout repos are refused.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .arcan_diff import cycle_sets
from .mixed_plan import dry_run
from .scc_dissolve import PLAN_ATTEMPTS, move_accept, prepare
from ..refactoring import scc_planner
from ..refactoring.inversion_facts import InversionFacts
from ..refactoring.strategies import SourceFacts
from ..tools.arcan_runner import select_jdk
from ..verification.effect_checker import _copy_repo

MAX_SIZE = 4
STOP_RULE = 10
POOL = Path(__file__).resolve().parents[2] / "configs" / "repos_pool.yaml"


def holdout() -> set:
    text = POOL.read_text(encoding="utf-8")
    return set(re.findall(r"project_id: ([\w.-]+), repo_url: \S+, split: holdout", text))


def _legal(repo: Path, work: Path, plan_once: Callable[[set], Dict[str, Any]]) -> Dict[str, Any]:
    """Plan, ask Spoon, ban what it refuses and plan again, as `make_plans` does for moves."""
    banned: set = set()
    for _ in range(PLAN_ATTEMPTS):
        found = plan_once(banned)
        if found["predicted_left"]:
            return {**found, "dry_run_ok": None, "why": None}
        verdict = dry_run(repo, found, work)
        if verdict["ok"] or not verdict.get("refused"):
            return {**found, "dry_run_ok": verdict["ok"], "why": verdict.get("why")}
        banned.add(verdict["refused"])
    return {**found, "dry_run_ok": False, "why": "refused %d times" % PLAN_ATTEMPTS}


def probe_repo(repo: Path, out: Path) -> List[Dict[str, Any]]:
    tree = out / "baseline_tree"
    if not tree.exists():
        _copy_repo(repo, tree)
    select_jdk(tree)
    base = prepare(tree, out)
    facts = SourceFacts(tree)
    inv = InversionFacts(base["snapshot"], facts)
    edges = scc_planner.top_level_edges(tuple(e) for e in base["edges"])
    arcan = cycle_sets(out / "arcan_before" / "arcan", "package")
    comps = [c for c in scc_planner.components(scc_planner.package_edges(edges, {})) if len(c) <= MAX_SIZE]

    def mixed(comp, blocked):
        pairs = inv.candidates(edges, comp)
        return lambda banned: scc_planner.plan(
            edges, comp, move_accept(facts, banned), inversions=[p for p in pairs if p[1] not in banned],
            blocked=blocked, sig=inv.signature_types)

    # Diagnostic only: what construction alone costs. Never dry-run, never counted.
    no_construction = lambda p, i, m: (lambda r: None if r and r.startswith("constructed") else r)(inv.blocked(p, i, m))
    rows = []
    for comp in comps:
        t0 = time.time()
        moves = _legal(tree, out / "work", lambda banned: scc_planner.plan(edges, comp, move_accept(facts, banned)))
        mix = _legal(tree, out / "work", mixed(comp, inv.blocked))
        diag = mixed(comp, no_construction)(set())
        rows.append({
            "repo": repo.name, "component": sorted(comp), "size": len(comp),
            "arcan_reported": any(comp <= c for c in arcan),
            "moves_only": _cell(moves), "mixed": _cell(mix),
            "mixed_no_construction": {"predicted_left": diag["predicted_left"],
                                      "inversions": diag.get("inversions")},
            "secs": round(time.time() - t0)})
    return rows


def _cell(r: Dict[str, Any]) -> Dict[str, Any]:
    return {"predicted_left": r["predicted_left"], "dry_run_ok": r["dry_run_ok"], "why": r["why"],
            "dissolvable": r["predicted_left"] == 0 and r["dry_run_ok"] is True,
            "moves": r["moves"], "inversions": r.get("inversions")}


def summarise(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    reported = [r for r in rows if r["arcan_reported"]]
    extra = [r for r in reported if r["mixed"]["dissolvable"] and not r["moves_only"]["dissolvable"]]
    return {"sccs": len(rows), "arcan_reported": len(reported),
            "moves_only_dissolvable": sum(r["moves_only"]["dissolvable"] for r in reported),
            "mixed_dissolvable": sum(r["mixed"]["dissolvable"] for r in reported),
            "mix_extra_dissolvable": len(extra),
            "stop_rule_passed": len(extra) >= STOP_RULE,
            "unreported_dissolvable_by_mix": sum(r["mixed"]["dissolvable"] for r in rows if not r["arcan_reported"]),
            "repos": sorted({r["repo"] for r in rows})}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repos", type=Path)
    ap.add_argument("out", type=Path)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    held = holdout()
    rows: List[Dict[str, Any]] = []
    failed: Dict[str, str] = {}
    lines = [l.split() for l in a.repos.read_text(encoding="utf-8").splitlines() if l.strip()]
    for parts in lines:
        repo = Path(parts[0])
        if repo.name in held:
            raise SystemExit("holdout repo in a discovery probe: %s" % repo.name)
        out = Path(parts[1]) if len(parts) > 1 else a.out / repo.name
        out.mkdir(parents=True, exist_ok=True)
        print("--- %s %s" % (repo.name, time.strftime("%H:%M")), flush=True)
        try:
            got = probe_repo(repo, out)
        except Exception as e:     # a repo that does not build is reported, not fatal
            failed[repo.name] = str(e)[:300]
            print("  failed:", failed[repo.name], flush=True)
            continue
        rows += got
        with (a.out / "rows.jsonl").open("a", encoding="utf-8") as f:
            for r in got:
                f.write(json.dumps(r) + "\n")
        print("  sccs<=%d: %d, moves %d, mixed %d" % (MAX_SIZE, len(got),
              sum(r["moves_only"]["dissolvable"] for r in got), sum(r["mixed"]["dissolvable"] for r in got)), flush=True)
    summary = {**summarise(rows), "failed": failed}
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
