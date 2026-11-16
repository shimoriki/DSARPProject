"""Model check for the agentic RefAgent arm: can this model plan a package-cycle repair?

    python hpc/smoke.py MODEL REPOS OUT [--base-url URL] [--api-key-env VAR]

LLM plans for three cycles the beam arm dissolved (Commons Exec's one, Commons Math's first two;
Commons Text's first by the beam's own selection rule), each dry-run by Spoon. A case passes when
the plan dissolves the cycle in the simulated graph and the Spoon dry run succeeds. Bar: 2 of 3.
The last line is `MODEL CHECK <model>: <passed> of <total> (bar 2)`; run_refagent.slurm reads it.
REPOS holds apache-commons-exec, apache-commons-math and apache-commons-text (see setup.sh).
"""
import argparse
import json
import os
import time
from pathlib import Path

from dsarp.agentic.run import make_llm_plans
from dsarp.experiments.scc_dissolve import prepare
from dsarp.models.providers import DEFAULT_BASE_URL, LocalProvider
from dsarp.refactoring import scc_planner
from dsarp.tools import arcan_runner
from dsarp.verification.effect_checker import _copy_repo

CASES = [("apache-commons-exec", [["org.apache.commons.exec", "org.apache.commons.exec.environment",
                                   "org.apache.commons.exec.launcher"]]),
         ("apache-commons-math", [["org.apache.commons.math4.legacy.stat.descriptive",
                                   "org.apache.commons.math4.legacy.stat.descriptive.moment"]]),
         ("apache-commons-text", None)]

ap = argparse.ArgumentParser()
ap.add_argument("model")
ap.add_argument("repos", type=Path)
ap.add_argument("out", type=Path)
ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
ap.add_argument("--api-key-env", default="DSARP_LLM_KEY")
a = ap.parse_args()
# Uncapped: the check measures planning, not whether a reasoning model fits its answer in 800 tokens.
model = LocalProvider(a.model, a.base_url, timeout=1800, uncapped=True,
                      api_key=os.environ.get(a.api_key_env) or "dsarp-local")
passed, total = 0, 0
for repo, targets in CASES:
    out = a.out / repo
    tree = out / "baseline_tree"
    out.mkdir(parents=True, exist_ok=True)
    if not tree.exists():
        _copy_repo(a.repos / repo, tree)
    print(repo, "jdk", arcan_runner.select_jdk(tree), flush=True)
    t0 = time.time()
    base = prepare(tree, out)
    print("  prepared in %ds" % (time.time() - t0), flush=True)
    if targets is None:
        edges = scc_planner.top_level_edges(tuple(e) for e in base["edges"])
        targets = [sorted(scc_planner.components(scc_planner.package_edges(edges, {}))[0])]
    plans = make_llm_plans(tree, base, model, targets, out / "work", rounds=3)
    (out / "llm_plans.json").write_text(json.dumps(plans, indent=1, default=str), encoding="utf-8")
    for p in plans:
        ok = bool(p.get("dissolves")) and (p.get("dry_run") or {}).get("ok", False)
        passed += ok
        total += 1
        print("  %s dissolves=%s dry_run=%s rounds=%d" % (p["component"], p.get("dissolves"),
              (p.get("dry_run") or {}).get("ok"), len(p.get("rounds") or [])), flush=True)
print("MODEL CHECK %s: %d of %d (bar 2)" % (a.model, passed, total), flush=True)
