"""Model check for the agentic RefAgent arm: can this model plan a package-cycle repair?

    python hpc/smoke.py MODEL REPOS OUT [--base-url URL] [--api-key-env VAR]

LLM plans for three package cycles Arcan reports on the baseline and the beam arm dissolved
(Commons Exec's one tangle, Commons Math's stat.descriptive pair, Commons Text's one cycle). Each
target must be one of Arcan's cycle clusters, or the check stops: it measures Arcan smells only.
A plan that passes the Spoon dry run is applied to a copy (Spoon, no facades), compiled, and Arcan
runs again. A case passes only when Arcan no longer reports a cycle holding two or more of the
target's packages (arcan_diff.cycles_dissolved). The graph prediction is printed beside it.
Bar: 2 of 3. The last line is `MODEL CHECK <model>: <passed> of <total> (bar 2)`;
run_refagent.slurm reads it. REPOS holds apache-commons-exec, -math and -text (see setup.sh).
"""
import argparse
import json
import os
import time
from pathlib import Path

from dsarp.agentic.run import make_llm_plans
from dsarp.experiments.arcan_diff import cycle_clusters
from dsarp.experiments.mixed_plan import arcan_verdict
from dsarp.experiments.scc_dissolve import prepare
from dsarp.models.providers import DEFAULT_BASE_URL, LocalProvider
from dsarp.tools import arcan_runner
from dsarp.verification.effect_checker import _copy_repo

CASES = [("apache-commons-exec", ["org.apache.commons.exec", "org.apache.commons.exec.environment",
                                  "org.apache.commons.exec.launcher"]),
         ("apache-commons-math", ["org.apache.commons.math4.legacy.stat.descriptive",
                                  "org.apache.commons.math4.legacy.stat.descriptive.moment"]),
         ("apache-commons-text", ["org.apache.commons.text", "org.apache.commons.text.lookup"])]

ap = argparse.ArgumentParser()
ap.add_argument("model")
ap.add_argument("repos", type=Path)
ap.add_argument("out", type=Path)
ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
ap.add_argument("--api-key-env", default="DSARP_LLM_KEY")
# Hosted free tiers: seconds between calls (60/limit-per-minute), and the longest 429 wait to sit out.
ap.add_argument("--min-interval", type=float, default=0)
ap.add_argument("--max-wait", type=float, default=300)
a = ap.parse_args()
# Uncapped: the check measures planning, not whether a reasoning model fits its answer in 800 tokens.
model = LocalProvider(a.model, a.base_url, timeout=1800, uncapped=True,
                      api_key=os.environ.get(a.api_key_env) or "dsarp-local",
                      min_interval=a.min_interval, max_wait=a.max_wait)
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
    clusters = cycle_clusters(out / "arcan_before" / "arcan")
    if sorted(targets) not in clusters:
        raise SystemExit("%s: target %s is not an Arcan cycle cluster; Arcan reports %s"
                         % (repo, targets, clusters))
    plans = make_llm_plans(tree, base, model, [targets], out / "work", rounds=3)
    for p in plans:
        if (p.get("dry_run") or {}).get("ok"):
            p["arcan"] = arcan_verdict(tree, p, out / "arcan_before" / "arcan", out / "arcan_check")
        ok = bool((p.get("arcan") or {}).get("dissolved"))
        passed += ok
        total += 1
        print("  %s predicted=%s dry_run=%s arcan_dissolved=%s rounds=%d %s" % (
            p["component"], p.get("dissolves"), (p.get("dry_run") or {}).get("ok"), ok,
            len(p.get("rounds") or []), (p.get("arcan") or {}).get("why") or ""), flush=True)
    (out / "llm_plans.json").write_text(json.dumps(plans, indent=1, default=str), encoding="utf-8")
print("MODEL CHECK %s: %d of %d (bar 2, Arcan-verified)" % (a.model, passed, total), flush=True)
