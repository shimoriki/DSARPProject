"""REAL tool closed loop: detect -> OpenRewrite refactor -> re-detect -> compare.

    1. DETECT     run a real smell tool on the repo
                  - Arcan 1.2.1  : mvn compile -> java -jar arcan.jar -p target/classes -all
                    (package + class Cyclic Dependency, Unstable Dependency, Hub-Like)
                  - DesigniteJava: java -jar DesigniteJava.jar -i <repo> -o <out>
                    (design smells incl. Cyclic-Dependent Modularization)
    2. PLAN       derive concrete class moves that break the detected cycles
    3. REFACTOR   copy the repo, generate an OpenRewrite recipe, RUN `mvn rewrite:run`
                  -> real source changes (classes relocated, imports/references rewritten)
    4. RE-DETECT  run the SAME tool again on the refactored copy
    5. COMPARE    per-smell-type delta: what the refactoring actually removed

Arcan is the better verifier for cyclic smells: it reasons about PACKAGE cycles, which
relocating a class genuinely dissolves. Designite's Cyclic-Dependent Modularization is a
class-level type cycle that survives a package move.

Needs: the full Arcan distribution (jar + lib/) and/or DesigniteJava.jar in tools/, Maven
(tools/apache-maven-*/ or PATH), a JDK, and a repo that compiles. Every step records the
real command + status; nothing is faked.
"""
from __future__ import annotations

import collections
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..tools.designite import DesigniteAdapter
from ..util import write_json
from .effect_checker import _copy_repo, _crossing_classes
from ..openrewrite.runner import (find_mvn, run_recipe, write_change_package_recipe,
                                  write_change_type_recipe, write_composite_recipe)

DETECTORS = ("arcan", "designite", "both")


def designite_jar() -> Optional[Path]:
    tools = Path(__file__).resolve().parent.parent.parent / "tools"
    jars = sorted(tools.glob("*esignite*.jar"))
    return jars[-1] if jars else None


def available_detectors() -> Dict[str, bool]:
    """Which real tools can actually run on this machine right now."""
    from ..tools.arcan_runner import arcan_jar
    return {"arcan": arcan_jar() is not None, "designite": designite_jar() is not None}


def run_designite(repo_path: Path, out_dir: Path, timeout: int = 2400) -> Dict[str, Any]:
    """Run DesigniteJava on a repo; parse its CSVs into counts + findings."""
    jar = designite_jar()
    if not jar:
        return {"ok": False, "status": "designite_jar_not_found", "smells": 0,
                "by_type": {}, "findings": []}
    out_dir = Path(out_dir)
    # Designite Professional REFUSES to run if the output folder is not empty
    # ("The specified output folder is not empty. Quitting.."), so a stale run would
    # silently block every later one. Always hand it a clean directory.
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["java", "-jar", str(jar), "-i", str(Path(repo_path).resolve()),
           "-o", str(out_dir.resolve())]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "timeout", "smells": 0, "by_type": {}, "findings": []}
    out_txt = (proc.stdout or "") + (proc.stderr or "")
    if "output folder is not empty" in out_txt:
        return {"ok": False, "status": "output_folder_not_empty", "smells": None,
                "by_type": {}, "findings": [],
                "note": "Designite refused to write into a non-empty output folder."}
    # Designite Professional writes ArchitectureSmells.csv + DesignSmells.csv (+ Implementation/
    # Testability); the free/community edition only writes designCodeSmells.csv.
    findings = []
    for name in ("ArchitectureSmells.csv", "DesignSmells.csv", "designCodeSmells.csv"):
        for csv_path in out_dir.rglob(name):
            findings.extend(DesigniteAdapter().import_findings(csv_path))
    counts = collections.Counter(f.smell_type for f in findings)
    return {"ok": proc.returncode == 0, "status": "ok" if proc.returncode == 0 else "failed",
            "smells": len(findings), "by_type": dict(counts),
            "findings": [{"smell_type": f.smell_type, "components": f.affected_components,
                          "component_level": f.component_level,
                          "related": (f.metrics or {}).get("related_components") or [],
                          "description": (f.metrics or {}).get("Description", "")}
                         for f in findings], "out_dir": str(out_dir),
            "command": " ".join(cmd), "tool": "DesigniteJava"}


def _run_arcan(repo_path: Path, out_dir: Path) -> Dict[str, Any]:
    from ..tools.arcan_runner import detect_with_arcan
    return detect_with_arcan(Path(repo_path), Path(out_dir),
                             compile_log=Path(out_dir) / "mvn_compile.log",
                             arcan_log=Path(out_dir) / "arcan_run.log")


def detect(repo_path: Path, out_dir: Path, detector: str = "both") -> Dict[str, Any]:
    """Run the chosen real detector(s). Uniform {smells, by_type, findings} record.

    `both` runs Arcan AND Designite and merges: Arcan contributes package-level
    architectural smells (cycles / unstable / hub-like), Designite contributes class-level
    design smells. Findings are tagged with their tool and `by_tool` keeps them separable.
    """
    repo_path, out_dir = Path(repo_path), Path(out_dir)
    if detector == "arcan":
        return _run_arcan(repo_path, out_dir)
    if detector == "designite":
        return run_designite(repo_path, out_dir)

    arcan = _run_arcan(repo_path, out_dir / "arcan")
    desig = run_designite(repo_path, out_dir / "designite")
    findings: List[Dict[str, Any]] = []
    for tool, res in (("Arcan", arcan), ("Designite", desig)):
        if res.get("measured", res.get("ok")):
            for f in res.get("findings", []):
                findings.append({**f, "tool": tool})
    counts = collections.Counter(f["smell_type"] for f in findings)
    by_tool = {}
    for tool, res in (("Arcan", arcan), ("Designite", desig)):
        m = bool(res.get("measured", res.get("ok")))
        by_tool[tool] = {"status": res.get("status"), "measured": m,
                         "smells": res.get("smells") if m else None,
                         "by_type": res.get("by_type") if m else {},
                         "note": res.get("note")}
    any_ok = any(v["measured"] for v in by_tool.values())
    return {"ok": any_ok, "status": "ok" if any_ok else "failed",
            "measured": any_ok,
            "smells": len(findings) if any_ok else None,
            "by_type": dict(counts), "findings": findings, "by_tool": by_tool,
            "compile": arcan.get("compile"), "tool": "Arcan 1.2.1 + DesigniteJava"}


def derive_moves_from_findings(repo_path: Path, findings: List[Dict[str, Any]],
                               max_moves: int = 30) -> List[Tuple[str, str]]:
    """Turn detected PACKAGE cycles into concrete (oldFQN -> newFQN) class moves.

    For a cycle over packages [A, B, ...] take each adjacent pair and move whichever
    direction has fewer crossing classes — that removes A's dependency on B (or B's on A)
    and dissolves the package cycle.
    """
    moves: List[Tuple[str, str]] = []
    seen_pairs = set()
    for f in findings:
        if "cyclic" not in (f.get("smell_type") or "").lower():
            continue
        comps = [c for c in (f.get("components") or []) if "." in c]
        # class-level findings carry FQNs; reduce them to their packages
        if (f.get("component_level") or "") == "class":
            comps = sorted({c.rsplit(".", 1)[0] for c in comps})
        for i in range(len(comps)):
            a_pkg, b_pkg = comps[i], comps[(i + 1) % len(comps)]
            if a_pkg == b_pkg or (a_pkg, b_pkg) in seen_pairs:
                continue
            seen_pairs.add((a_pkg, b_pkg))
            seen_pairs.add((b_pkg, a_pkg))
            moves += _cheapest_direction(Path(repo_path), a_pkg, b_pkg)
            if len(moves) >= max_moves:
                break
        if len(moves) >= max_moves:
            break
    return _dedupe_moves(moves)[:max_moves]


def _dedupe_moves(moves: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """One destination per class.

    Overlapping cycles can assign the SAME class two different targets (e.g. X -> a.X and
    X -> b.X). OpenRewrite would then emit contradictory ChangeType rules and the rewritten
    code will not compile, so keep only the first destination proposed for each class.
    """
    out: List[Tuple[str, str]] = []
    claimed = set()
    for old, new in moves:
        if old in claimed or old == new:
            continue
        claimed.add(old)
        out.append((old, new))
    return out


def plan_package_merges(repo_path: Path, findings: List[Dict[str, Any]],
                        max_merges: int = 0) -> List[Tuple[str, str]]:
    """Compile-safe plan: merge the smaller package of each cyclic pair into the larger.

    Dissolving package A into B removes A from the package graph entirely, so any cycle
    that ran through A is gone — and because every class in A moves together, their
    intra-package references still resolve.
    """
    from ..refactoring.params import RefactoringParams
    max_merges = max_merges or RefactoringParams.load().max_package_merges
    sizes: Dict[str, int] = {}

    def size(pkg: str) -> int:
        if pkg not in sizes:
            sizes[pkg] = len(_package_classes(Path(repo_path), pkg))
        return sizes[pkg]

    merges: List[Tuple[str, str]] = []
    gone: set = set()
    for f in findings:
        if "cyclic" not in (f.get("smell_type") or "").lower():
            continue
        comps = [c for c in (f.get("components") or []) if "." in c]
        if (f.get("component_level") or "") == "class":
            comps = sorted({c.rsplit(".", 1)[0] for c in comps})
        for i in range(len(comps)):
            a_pkg, b_pkg = comps[i], comps[(i + 1) % len(comps)]
            if a_pkg == b_pkg or a_pkg in gone or b_pkg in gone:
                continue
            if not size(a_pkg) or not size(b_pkg):
                continue
            if a_pkg.startswith(b_pkg + "."):
                src, dst = a_pkg, b_pkg      # flatten the sub-package into its parent
            elif b_pkg.startswith(a_pkg + "."):
                src, dst = b_pkg, a_pkg
            else:
                src, dst = ((a_pkg, b_pkg) if size(a_pkg) <= size(b_pkg)
                            else (b_pkg, a_pkg))   # merge the smaller package into the larger
            # merging a parent INTO its own descendant would nest a package inside itself
            if dst.startswith(src + "."):
                continue
            if not _merge_is_safe(Path(repo_path), src, dst):
                continue
            merges.append((src, dst))
            gone.add(src)
            if len(merges) >= max_merges:
                return merges
    return merges


def _merge_is_safe(repo_path: Path, src: str, dst: str) -> bool:
    """Reject package merges that cannot possibly compile.

    Two ways a merge is fatal:
      * simple-name collision — Java forbids two types with the same name in one package,
        and libraries often keep a legacy `x.Foo` alongside a modern `x.routines.Foo`;
      * `src` has sub-packages — ChangePackage rewrites the whole `src.` prefix, so every
        descendant's FQN shifts too and any reference to them dangles.
    """
    src_names = {p.stem for p in _package_classes(repo_path, src)}
    dst_names = {p.stem for p in _package_classes(repo_path, dst)}
    if src_names & dst_names:
        return False
    return not _has_subpackages(repo_path, src)


def _has_subpackages(repo_path: Path, pkg: str) -> bool:
    prefix = f"package {pkg}."
    for jf in Path(repo_path).rglob("*.java"):
        p = str(jf).replace("\\", "/")
        if "/test/" in p or "/target/" in p:
            continue
        try:
            if prefix in jf.read_text(encoding="utf-8", errors="ignore")[:2000]:
                return True
        except OSError:
            continue
    return False


def _package_classes(repo_path: Path, pkg: str) -> List[Path]:
    """Source files declaring `package <pkg>;` (production code only)."""
    out = []
    for jf in Path(repo_path).rglob("*.java"):
        p = str(jf).replace("\\", "/")
        if "/test/" in p or "/target/" in p:
            continue
        try:
            head = jf.read_text(encoding="utf-8", errors="ignore")[:2000]
        except OSError:
            continue
        if f"package {pkg};" in head:
            out.append(jf)
    return out


def _cheapest_direction(repo_path: Path, a_pkg: str, b_pkg: str) -> List[Tuple[str, str]]:
    """Move the smaller set of crossing classes, so the cheaper edge direction disappears."""
    a_to_b = _crossing_classes(repo_path, a_pkg, b_pkg)
    b_to_a = _crossing_classes(repo_path, b_pkg, a_pkg)
    if not a_to_b and not b_to_a:
        return []
    if b_to_a and (not a_to_b or len(b_to_a) <= len(a_to_b)):
        movers, target = b_to_a, a_pkg
    else:
        movers, target = a_to_b, b_pkg
    return [(fqn, f"{target}.{fqn.rsplit('.', 1)[-1]}") for fqn in movers]


def derive_moves(repo_path: Path, suggestion: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Concrete (oldFQN -> newFQN) moves that break a suggestion's target boundary."""
    b = suggestion.get("target_boundary", {})
    a_pkg, b_pkg = b.get("from"), b.get("to")
    if not a_pkg or not b_pkg:
        return []
    return _cheapest_direction(Path(repo_path), a_pkg, b_pkg)


def _types_touched(plan) -> set:
    """Fully-qualified types a plan's recipe entries will rewrite."""
    out = set()
    for e in plan.entries:
        o = e.options
        for key in ("oldFullyQualifiedTypeName", "fullyQualifiedClassName"):
            if o.get(key):
                out.add(o[key])
        if o.get("oldPackageName"):
            out.add(o["oldPackageName"] + ".*")
    return out


def explain_no_moves(repo_path: Path, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Say WHY no compile-safe relocation exists, instead of silently doing nothing.

    The common case: every detected cycle is a CLASS cycle inside one package. Relocating
    packages cannot dissolve that — two classes in the same package referring to each other
    stay tangled wherever the package lives. Breaking it needs dependency inversion (extract
    an interface at the seam), for which OpenRewrite ships no stock recipe.
    """
    cyclic = [f for f in findings if "cyclic" in (f.get("smell_type") or "").lower()]
    cross_pkg, intra_pkg = 0, 0
    blocked: List[str] = []
    for f in cyclic:
        comps = [c for c in (f.get("components") or []) if "." in c]
        pkgs = ({c.rsplit(".", 1)[0] for c in comps}
                if (f.get("component_level") or "") == "class" else set(comps))
        if len(pkgs) > 1:
            cross_pkg += 1
        else:
            intra_pkg += 1
    # for the cross-package ones, report which merges the safety guards rejected
    for f in cyclic:
        comps = [c for c in (f.get("components") or []) if "." in c]
        pkgs = sorted({c.rsplit(".", 1)[0] for c in comps}
                      if (f.get("component_level") or "") == "class" else set(comps))
        for i in range(len(pkgs)):
            a, b = pkgs[i], pkgs[(i + 1) % len(pkgs)]
            if a == b or not _package_classes(Path(repo_path), a):
                continue
            if not _merge_is_safe(Path(repo_path), a, b):
                names = ({p.stem for p in _package_classes(Path(repo_path), a)} &
                         {p.stem for p in _package_classes(Path(repo_path), b)})
                reason = (f"same-named classes in both packages: {sorted(names)[:3]}" if names
                          else f"{a} has sub-packages")
                entry = f"{a} -> {b}: {reason}"
                if entry not in blocked:
                    blocked.append(entry)
    if cyclic and not cross_pkg:
        note = (f"All {intra_pkg} cyclic smells are class cycles INSIDE a single package. "
                "Relocating packages cannot dissolve them — breaking an intra-package type "
                "cycle needs dependency inversion (extract an interface at the seam), which "
                "OpenRewrite has no stock recipe for. Reported as requires_source_inspection.")
    elif blocked:
        note = ("Cross-package cycles exist, but every candidate merge was rejected as unsafe: "
                + "; ".join(blocked[:3]))
    elif not cyclic:
        note = "No cyclic smells were detected, so there was nothing to relocate."
    else:
        note = "No compile-safe relocation could be derived for the detected cycles."
    return {"note": note, "cyclic_findings": len(cyclic),
            "cross_package_cycles": cross_pkg, "intra_package_cycles": intra_pkg,
            "blocked_merges": blocked[:10],
            "verification_status": "requires_source_inspection"}


def refactor_with_openrewrite_and_verify(cfg: Config, project_id: str, repo_path: Path,
                                         suggestions: Optional[List[Dict[str, Any]]] = None,
                                         max_moves: int = 30,
                                         detector: str = "both",
                                         strategy: str = "merge_package",
                                         keep_copy: bool = False) -> Dict[str, Any]:
    """Full real loop. Returns a step-by-step record with before/after tool smells."""
    repo_path = Path(repo_path)
    out = cfg.data_dir / "outputs" / project_id
    steps: List[Dict[str, Any]] = []
    tool_name = {"arcan": "Arcan 1.2.1", "designite": "DesigniteJava"}.get(
        detector, "Arcan 1.2.1 + DesigniteJava")

    # 1) DETECT (real tool)
    before = detect(repo_path, out / f"{detector}_before", detector)
    steps.append({"step": "detect", "tool": tool_name, "status": before["status"],
                  "smells": before.get("smells"), "by_type": before.get("by_type"),
                  "by_tool": before.get("by_tool"),
                  "compile": (before.get("compile") or {}).get("status")})

    # 2) PLAN a transformation for EVERY detected smell type.
    #    - cyclic smells      -> package merges (ChangePackage), handled here
    #    - all other smells   -> dsarp.refactoring.strategies (split / consolidate / move /
    #                            delete dead code), each emitting stock recipe entries
    #    Strategies that cannot be automated report an evidence-backed reason instead.
    from ..refactoring.strategies import RecipeEntry, SourceFacts, plan_for

    findings = before.get("findings", [])
    facts = SourceFacts(repo_path)
    entries: List[Any] = []
    plans: List[Dict[str, Any]] = []
    pre_imports: Dict[str, List[str]] = {}
    claimed: set = set()

    merges = plan_package_merges(repo_path, findings) if strategy == "merge_package" else []
    for src, dst in merges:
        entries.append(RecipeEntry("org.openrewrite.java.ChangePackage",
                                   {"oldPackageName": src, "newPackageName": dst,
                                    "recursive": False}))
    if merges:
        plans.append({"smell_type": "Cyclic Dependency", "refactoring": "Merge Package",
                      "components": [f"{s} -> {d}" for s, d in merges], "applicable": True,
                      "reason": f"{len(merges)} package merge(s) dissolve the detected cycles",
                      "recipes": ["org.openrewrite.java.ChangePackage"],
                      "operations": len(merges), "stock_recipes": True,
                      "verification_status": "planned"})

    seen_keys = set()
    for f in findings:
        key = (f.get("smell_type"), tuple(f.get("components") or [])[:3])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        p = plan_for(facts, f)
        if p is None:
            continue
        # Two refactorings touching the SAME type in one OpenRewrite pass interfere: e.g.
        # extracting an interface from a class another plan is relocating leaves the new
        # interface pointing at the old package. First plan to claim a type wins.
        touched = _types_touched(p)
        if p.applicable and touched & claimed:
            d = p.as_dict()
            d.update(applicable=False,
                     reason="conflicts with another refactoring already scheduled for "
                            f"{sorted(touched & claimed)[0]} in this pass; deferred to the "
                            "next iteration of the loop")
            plans.append(d)
            continue
        plans.append(p.as_dict())
        if p.applicable:
            claimed |= touched
            entries.extend(p.entries)
            pre_imports.update(p.pre_imports)

    applicable = [p for p in plans if p["applicable"]]
    by_smell = collections.Counter(p["smell_type"] for p in applicable)
    steps.append({"step": "plan_refactorings", "tool": "DSARP",
                  "status": "ok" if entries else "none",
                  "smell_types_detected": len({p["smell_type"] for p in plans}),
                  "smell_types_actionable": len(by_smell),
                  "plans_applicable": len(applicable),
                  "plans_not_applicable": len(plans) - len(applicable),
                  "recipe_operations": len(entries),
                  "by_smell_type": dict(by_smell), "plans": plans})

    if entries:
        return _apply_and_verify(cfg, project_id, repo_path, out, steps, before, detector,
                                 tool_name, entries, kind="composite", plans=plans,
                                 pre_imports=pre_imports, keep_copy=keep_copy)

    moves = derive_moves_from_findings(repo_path, findings, max_moves)
    source = "tool_findings"
    if not moves and suggestions:
        for s in suggestions:
            if "cyclic" in (s.get("smell_type", "") or "").lower():
                moves += derive_moves(repo_path, s)
            if len(moves) >= max_moves:
                break
        moves = _dedupe_moves(moves)[:max_moves]
        source = "suggestions"
    steps.append({"step": "plan_moves", "tool": "DSARP", "status": "ok", "derived_from": source,
                  "moves": [f"{o} -> {n}" for o, n in moves[:20]], "count": len(moves)})

    if not moves:
        why = explain_no_moves(repo_path, before.get("findings", []))
        steps.append({"step": "openrewrite", "status": "skipped",
                      "note": why["note"], "diagnosis": why})
        report = {"project_id": project_id, "detector": detector, "tool": tool_name,
                  "steps": steps, "smells_before": before.get("smells"),
                  "verification_status": "not_applicable_no_safe_refactoring",
                  "diagnosis": why,
                  "findings_before": before.get("findings", [])[:200],
                  "by_tool_before": before.get("by_tool"),
                  "by_type_before": before.get("by_type")}
        write_json(out / "openrewrite_loop_report.json", report)
        write_json(out / f"loop_{detector}_report.json", report)
        return report

    return _apply_and_verify(cfg, project_id, repo_path, out, steps, before, detector,
                             tool_name, moves, kind="class", keep_copy=keep_copy)


def _apply_and_verify(cfg: Config, project_id: str, repo_path: Path, out: Path,
                      steps: List[Dict[str, Any]], before: Dict[str, Any], detector: str,
                      tool_name: str, plan: List[Any], kind: str = "class",
                      plans: Optional[List[Dict[str, Any]]] = None,
                      pre_imports: Optional[Dict[str, List[str]]] = None,
                      keep_copy: bool = False) -> Dict[str, Any]:
    """Steps 3-5: run OpenRewrite on a copy, re-detect with the same tool(s), compare."""
    # 3) REFACTOR — copy repo, generate recipe, RUN OpenRewrite (real source changes)
    copy = _copy_repo(repo_path, out / "openrewrite_copy")
    if pre_imports:
        from ..refactoring.strategies import apply_pre_imports
        pre = apply_pre_imports(copy, pre_imports)
        steps.append({"step": "prepare_imports", "tool": "DSARP", "status": "ok",
                      "note": "made same-package references explicit so relocated classes "
                              "still resolve their former siblings",
                      **pre})
    if kind == "composite":
        recipe = write_composite_recipe(copy, plan)
    elif kind == "package":
        recipe = write_change_package_recipe(copy, plan)
    else:
        recipe = write_change_type_recipe(copy, plan)
    orw = run_recipe(copy, dry_run=False, log_path=out / "openrewrite_run.log")
    steps.append({"step": "openrewrite", "tool": "OpenRewrite (mvn rewrite:run)",
                  "status": orw["status"], "mvn": orw.get("mvn"),
                  "changed_files": orw.get("changed_files"),
                  "changed_count": len(orw.get("changed_files") or []),
                  "recipe_path": str(recipe), "note": orw.get("note")})

    # 4) RE-DETECT with the SAME tool on the refactored copy
    after = detect(copy, out / f"{detector}_after", detector)
    steps.append({"step": "re-detect", "tool": tool_name, "status": after["status"],
                  "smells": after.get("smells"), "by_type": after.get("by_type"),
                  "by_tool": after.get("by_tool"),
                  "compile": (after.get("compile") or {}).get("status")})

    # 5) COMPARE — only tools that measured BOTH sides may claim a delta. A tool that
    # could not run after the refactoring (e.g. Arcan when the rewritten code no longer
    # compiles) reports "unmeasurable", never a spurious drop to zero.
    per_tool = {}
    for tool, b_rec in (before.get("by_tool") or {}).items():
        a_rec = (after.get("by_tool") or {}).get(tool) or {}
        both = bool(b_rec.get("measured")) and bool(a_rec.get("measured"))
        per_tool[tool] = {
            "before": b_rec.get("smells"), "after": a_rec.get("smells"), "measured": both,
            "removed": (b_rec.get("smells") - a_rec.get("smells")) if both else None,
            "note": None if both else (a_rec.get("note") or "could not be measured after refactoring"),
        }
    measured_tools = {t for t, v in per_tool.items() if v["measured"]} or None
    if measured_tools is None:            # single-detector run: fall back to top-level flags
        both_ok = bool(before.get("measured", before.get("ok"))) and \
                  bool(after.get("measured", after.get("ok")))
    else:
        both_ok = True
    # smell-type deltas only over tools that measured both sides
    def _by_type(rec):
        if measured_tools is None:
            return rec.get("by_type", {})
        merged = collections.Counter()
        for t in measured_tools:
            merged.update(((rec.get("by_tool") or {}).get(t) or {}).get("by_type") or {})
        return dict(merged)
    b_by, a_by = _by_type(before), _by_type(after)
    delta = {k: a_by.get(k, 0) - b_by.get(k, 0) for k in set(b_by) | set(a_by)} if both_ok else {}
    removed = (sum(b_by.values()) - sum(a_by.values())) if both_ok else None
    verification = "verified" if both_ok else "unverified_build_broken"
    steps.append({"step": "compare", "tool": "DSARP",
                  "status": "ok" if both_ok else "unverified",
                  "smells_before": sum(b_by.values()) if both_ok else before.get("smells"),
                  "smells_after": sum(a_by.values()) if both_ok else None,
                  "delta_by_type": delta, "per_tool": per_tool,
                  "verification_status": verification, "removed": removed,
                  "note": None if both_ok else
                  "The refactored code did not build, so the after-state could not be measured."})

    report = {"project_id": project_id, "detector": detector, "tool": tool_name, "steps": steps,
              "moves": len(plan), "strategy": kind, "openrewrite": orw["status"],
              "verification_status": verification,
              "build_after_refactoring": (after.get("compile") or {}).get("status"),
              "smells_before": sum(b_by.values()) if both_ok else before.get("smells"),
              "smells_after": sum(a_by.values()) if both_ok else None,
              "by_type_before": b_by, "by_type_after": a_by, "delta_by_type": delta,
              "by_tool_before": before.get("by_tool"), "by_tool_after": after.get("by_tool"),
              "per_tool": per_tool,
              "findings_before": before.get("findings", [])[:200],
              "findings_after": after.get("findings", [])[:200],
              "recipe_path": str(recipe), "changed_files": orw.get("changed_files"),
              "plans": plans or []}
    write_json(out / "openrewrite_loop_report.json", report)
    write_json(out / f"loop_{detector}_report.json", report)
    if keep_copy:
        # The iterative loop feeds this refactored tree into the next pass; deleting it here
        # would make every pass restart from the original source.
        report["refactored_copy"] = str(copy)
    else:
        shutil.rmtree(copy, ignore_errors=True)
    return report
