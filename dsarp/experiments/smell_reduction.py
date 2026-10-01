"""Measure Designite smell reduction: counts by type before, the change applied, counts after.

The architecture smells this project has spent its effort on are 10 of commons-validator's 257
production-code findings. The majority are implementation smells -- Magic Number alone is 68, a
quarter of everything Designite reports -- and design smells are another 81. So "most smells
addressed" is mostly a question about those, measured by re-running the detector.

Two things this harness refuses to do, both learned here the hard way:

  * it will not report a reduction from a tree that did not build. A smell count falls reliably
    when the code stops compiling, and a run whose build failed is reported as such;
  * it will not compare different detector runs of different code. Before and after come from the
    same Designite version on the same machine, over the same source roots.

DesigniteJava is compiled for Java 22 (class file 66) and the project's default JDK is 17, where
it dies with UnsupportedClassVersionError. The JDK is selected explicitly for that reason.
"""
from __future__ import annotations

import collections
import csv
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..openrewrite.runner import run_recipe

# Stock static-analysis recipes ship in their own artifact, which the plugin does not carry.
STATIC_ANALYSIS = "org.openrewrite.recipe:rewrite-static-analysis:2.41.1"
from ..tools.arcan_runner import compile_repo, jdk_home_for, run_tests
from ..verification import gates
from ..verification.effect_checker import _copy_repo

CATEGORIES = ("ImplementationSmells", "DesignSmells", "ArchitectureSmells",
              "TestabilitySmells")


def designite_jar() -> Optional[Path]:
    for root in (Path(__file__).resolve().parents[2] / "tools",
                 Path(r"C:/Users/Rohit/PycharmProjects/dsarp-project/tools")):
        jar = root / "DesigniteJava.jar"
        if jar.exists():
            return jar
    return None


def measure_smells(repo: Path, out_dir: Path, timeout: int = 2400) -> Dict[str, Any]:
    """Designite's own counts, by category and by smell type.

    Test code is excluded from the headline twice over, because Designite reports it twice over:

      * the TestabilitySmells category, which is only about test code;
      * findings in the other three categories that are *located in* a test source file. These
        are easy to miss and there are 25 of them in commons-validator, a ninth of the total.
        Counting them would let a change look good by touching nothing that ships, and
        Unutilized Abstraction turns out to be 14 test classes to 3 production ones.

    A finding is test code when its file sits under `/src/test/`, the Maven and Gradle
    convention; all 25 in commons-validator do. `test_code` is reported rather than discarded,
    so a reduction cannot quietly come from there.
    """
    jar = designite_jar()
    if not jar:
        return {"ok": False, "why": "DesigniteJava.jar not found"}
    jdk = jdk_home_for("26", "25", "24", "23", "22")
    if not jdk:
        return {"ok": False, "why": "Designite needs a JDK 22 or newer; none installed"}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run([str(Path(jdk) / "bin" / "java"), "-jar", str(jar),
                               "-i", str(repo), "-o", str(out_dir)],
                              capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"ok": False, "why": "designite failed: %s" % str(exc)[:160]}
    by_type: Dict[str, int] = collections.Counter()
    by_cat: Dict[str, int] = {}
    test_code = 0
    for name in CATEGORIES:
        f = out_dir / (name + ".csv")
        if not f.exists():
            continue
        rows = list(csv.DictReader(f.open(encoding="utf-8-sig")))
        by_cat[name] = len(rows)
        if name == "TestabilitySmells":
            continue
        for r in rows:
            if not r.get("Smell"):
                continue
            if is_test_code(r.get("File")):
                test_code += 1
                continue
            by_type[r["Smell"]] += 1
    if not by_cat:
        return {"ok": False, "why": "designite produced no CSVs",
                "tail": (proc.stdout or "")[-500:]}
    return {"ok": True, "production_smells": sum(by_type.values()),
            "test_code_smells": test_code, "by_category": by_cat,
            "by_type": dict(by_type)}


def is_test_code(path: Optional[str]) -> bool:
    """A finding in a test source root. `/src/test/` is the Maven and Gradle convention.

    Deliberately not a match on `/test/` anywhere in the path: a production package genuinely
    named `test` would be excluded by that, and the smell would vanish from the denominator
    without anyone noticing.
    """
    return bool(path) and "/src/test/" in Path(path).as_posix()


def deltas(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Per-type change, and the honest total. Negative means fewer smells."""
    bt, at = before.get("by_type") or {}, after.get("by_type") or {}
    per = {k: at.get(k, 0) - bt.get(k, 0) for k in sorted(set(bt) | set(at))
           if at.get(k, 0) != bt.get(k, 0)}
    return {"d_production": (after.get("production_smells") or 0)
                            - (before.get("production_smells") or 0),
            "before": before.get("production_smells"),
            "after": after.get("production_smells"),
            "by_type_delta": per,
            "removed": -sum(v for v in per.values() if v < 0),
            "introduced": sum(v for v in per.values() if v > 0)}


def apply_recipes(repo: Path, recipe_names: List[str], out_dir: Path,
                  before: Optional[Dict[str, Any]] = None,
                  baseline_tests: Optional[Dict[str, Any]] = None,
                  run_the_tests: bool = True) -> Dict[str, Any]:
    """Run OpenRewrite recipes on a copy and report what Designite says afterwards.

    Stock recipes are named directly rather than wrapped in a generated rewrite.yml: the plugin
    accepts a comma-separated activeRecipes list, so there is nothing to synthesise and nothing
    to get wrong in the YAML.
    """
    repo, out_dir = Path(repo), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if before is None:
        before = measure_smells(repo, out_dir / "designite_before")
    if not before.get("ok"):
        return {"ok": False, "why": "baseline measurement failed: %s" % before.get("why")}
    work = out_dir / "work"
    shutil.rmtree(work, ignore_errors=True)
    copy = _copy_repo(repo, work / "copy")
    row: Dict[str, Any] = {"recipes": recipe_names,
                           "before_production_smells": before["production_smells"]}
    t0 = time.time()
    try:
        res = _run_stock(copy, recipe_names, work / "rewrite.log")
        row["rewrite_status"] = res.get("status")
        row["files_changed"] = len(res.get("changed_files") or [])
        if res.get("status") != "changed":
            row.update(ok=False, why=str(res.get("errors") or res.get("status"))[:240],
                       secs=round(time.time() - t0))
            return row
        build = compile_repo(copy, log_path=work / "compile.log", goal="test-compile")
        row["compile"] = build.get("status")
        if not build.get("ok"):
            # A smell count falls reliably when the code stops compiling.
            row.update(ok=False, why=(build.get("javac_errors") or [""])[0][:240],
                       secs=round(time.time() - t0))
            return row
        after = measure_smells(copy, work / "designite_after")
        if not after.get("ok"):
            row.update(ok=False, why="after-measurement failed: %s" % after.get("why"))
            return row
        row["delta"] = deltas(before, after)
        if run_the_tests:
            t = run_tests(copy, log_path=work / "tests.log")
            row["tests"] = {k: t.get(k) for k in ("status", "tests_run", "failures", "errors")}
            row["behavioural"] = gates.behavioural(baseline_tests or {}, t)
            row["tests_ok"] = row["behavioural"]["ok"]
        row["ok"] = bool(row["delta"]["d_production"] < 0
                         and (not run_the_tests or row.get("tests_ok")))
        row["secs"] = round(time.time() - t0)
        if row["ok"]:
            row["patch"] = str(_write_patch(repo, copy, out_dir / "patches", recipe_names))
        return row
    finally:
        shutil.rmtree(work / "copy", ignore_errors=True)


def _run_stock(copy: Path, recipe_names: List[str], log_path: Path) -> Dict[str, Any]:
    """rewrite:run with stock recipes, no generated configuration."""
    (copy / "rewrite.yml").write_text(
        "---\ntype: specs.openrewrite.org/v1beta/recipe\n"
        "name: com.dsarp.SmellReduction\ndisplayName: DSARP smell reduction\n"
        "description: Stock static-analysis recipes selected by measured Designite smell type.\n"
        "recipeList:\n" + "".join("  - %s\n" % r for r in recipe_names), encoding="utf-8")
    return run_recipe(copy, recipe_name="com.dsarp.SmellReduction", log_path=log_path,
                      recipe_artifacts=[STATIC_ANALYSIS])


def _write_patch(original: Path, copy: Path, out_dir: Path, recipes: List[str]) -> Path:
    import difflib
    index = lambda root: {p.relative_to(root).as_posix(): p
                          for p in Path(root).rglob("*.java")
                          if "target" not in p.relative_to(root).parts}
    a, b = index(original), index(copy)
    chunks = []
    for rel in sorted(set(a) | set(b)):
        old = a[rel].read_text(encoding="utf-8", errors="ignore").splitlines(True) if rel in a else []
        new = b[rel].read_text(encoding="utf-8", errors="ignore").splitlines(True) if rel in b else []
        if old != new:
            chunks.append("".join(difflib.unified_diff(old, new, fromfile="a/" + rel,
                                                       tofile="b/" + rel, n=3)))
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / ("smells__%s.patch" % "_".join(r.rsplit(".", 1)[-1] for r in recipes)[:80])
    p.write_text("# recipes: %s\n" % ", ".join(recipes) + "".join(chunks), encoding="utf-8")
    return p
