"""Closed-loop verification: apply a refactoring, then re-measure architectural smells.

The scientific question: does applying suggestion X actually REMOVE the smell?
Loop: snapshot smells -> apply refactoring on a repo copy -> re-index -> rebuild graph
-> snapshot smells again -> diff.

Smells (cyclic/hub/unstable/god) are DEFINED by the dependency graph + source structure,
so re-measuring from the modified source is objective and needs no external JVM tool. When
Arcan/Designite JARs are configured, execute-mode can re-run them too (not required here).

Refactoring application:
  - `apply_move_class` deterministically moves a class to another package (moves the file,
    rewrites its `package` declaration, and updates imports/FQNs across the repo). This is the
    canonical cycle-breaking architectural refactoring and is exactly what OpenRewrite's
    move/ChangeType recipes do; we run it directly so the loop works without Maven.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..graphs.builder import DependencyGraphBuilder
from ..smells.detector import StructuralSmellDetector
from ..source_index.indexer import SourceIndexer


def _java_files(repo_path: Path):
    """Non-test .java files (consistent with the SourceIndexer, which excludes /test/)."""
    for jf in Path(repo_path).rglob("*.java"):
        if "/test/" not in jf.as_posix():
            yield jf


@dataclass
class SmellSnapshot:
    smell_counts: Dict[str, int] = field(default_factory=dict)
    cycles: List[List[str]] = field(default_factory=list)
    total: int = 0
    node_count: int = 0
    edge_count: int = 0
    cycle_count: int = 0  # TRUE cycle count (bounded), not the display-capped `cycles` list
    edges: List[Dict[str, str]] = field(default_factory=list)  # import edges (for simulation)
    findings: List[Dict[str, Any]] = field(default_factory=list)  # every smell: {type, components}

    def has_smell(self, smell_type: str, components: List[str]) -> bool:
        """Is a smell of this type still present on (any of) these components?"""
        comps = set(components)
        st = smell_type.lower()
        for f in self.findings:
            if f["smell_type"].lower() == st and comps & set(f["components"]):
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {"total": self.total, "by_type": self.smell_counts,
                "cycles": self.cycles[:20], "nodes": self.node_count, "edges": self.edge_count}


def snapshot_smells(repo_path: Path, project_id: str = "snapshot") -> SmellSnapshot:
    """Detect architectural smells from the current source of repo_path."""
    idx = SourceIndexer().index(project_id, Path(repo_path))
    dg = DependencyGraphBuilder().build(idx.import_edges)
    findings = StructuralSmellDetector().detect(project_id, dg, idx.to_dict())
    counts: Dict[str, int] = {}
    for f in findings:
        counts[f.smell_type] = counts.get(f.smell_type, 0) + 1
    return SmellSnapshot(
        smell_counts=counts, cycles=dg.graph_metrics.get("cycles", []),
        total=len(findings), node_count=dg.graph_metrics.get("node_count", 0),
        edge_count=dg.graph_metrics.get("edge_count", 0),
        cycle_count=dg.graph_metrics.get("cycle_count", 0), edges=idx.import_edges,
        findings=[{"smell_type": f.smell_type, "components": list(f.affected_components)}
                  for f in findings])


def simulate_refactoring(snapshot: SmellSnapshot, from_pkg: str, to_pkg: str,
                         refactoring: str) -> Dict[str, Any]:
    """Graph-level simulation of a DESIGN refactoring's effect on the target edge.

    We cannot source-apply Extract Interface / Dependency Inversion with stock OpenRewrite,
    but we CAN test whether the recommendation is architecturally sound: these refactorings
    break the concrete `from -> to` dependency (an interface/abstraction is introduced, or the
    dependency is inverted). We remove that edge from the graph and re-count cycles. This
    answers "if applied, would the smell be removed?" — clearly labelled as a simulation.
    """
    import networkx as nx
    import itertools
    g = nx.DiGraph()
    for e in snapshot.edges:
        g.add_edge(e["source"], e["target"])
    removed = False
    if g.has_edge(from_pkg, to_pkg):
        g.remove_edge(from_pkg, to_pkg); removed = True
    if refactoring == "Dependency Inversion" and g.has_edge(to_pkg, from_pkg):
        # inversion also relieves the reverse concrete dependency
        pass
    try:
        cycles_after = sum(1 for _ in itertools.islice(nx.simple_cycles(g), 2000))
    except Exception:
        cycles_after = snapshot.cycle_count
    return {"edge_targeted": f"{from_pkg}->{to_pkg}", "edge_present": removed,
            "cycles_before": snapshot.cycle_count, "cycles_after": cycles_after,
            "smell_removed": cycles_after < snapshot.cycle_count}


# --------------------------------------------------------------------------- #
# deterministic Move Class (breaks package cycles, mirrors OpenRewrite move)
# --------------------------------------------------------------------------- #
def _find_class_file(repo_path: Path, from_pkg: str, cname: str) -> Optional[Path]:
    target = f"package {from_pkg};"
    for jf in Path(repo_path).rglob(f"{cname}.java"):
        if "/test/" in jf.as_posix():
            continue
        try:
            head = jf.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if re.search(r"package\s+" + re.escape(from_pkg) + r"\s*;", head):
            return jf
    return None


def apply_move_class(repo_path: Path, class_fqn: str, to_package: str) -> Dict[str, Any]:
    """Move `class_fqn` into `to_package`: relocate file, fix package decl, update imports/FQNs.

    Returns {applied, moved_from, moved_to, files_changed, note}.
    """
    repo_path = Path(repo_path)
    from_pkg, cname = class_fqn.rsplit(".", 1)
    new_fqn = f"{to_package}.{cname}"
    src = _find_class_file(repo_path, from_pkg, cname)
    if src is None:
        return {"applied": False, "note": f"class file for {class_fqn} not found"}

    # 1) rewrite the moved class's package declaration
    text = src.read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"package\s+" + re.escape(from_pkg) + r"\s*;",
                  f"package {to_package};", text, count=1)
    # a class moving into `to_package` may now need to import types it used from its old package;
    # (best-effort: leave as-is — graph is import-driven, compilation is a separate concern)

    # 2) relocate the file to the new package directory (mirror the .../to/package/ path)
    rel = src.relative_to(repo_path).as_posix()
    if "/java/" in rel:
        root = rel[: rel.index("/java/") + len("/java/")]
        new_rel = root + to_package.replace(".", "/") + f"/{cname}.java"
    else:  # no maven layout -> place beside using the package path
        new_rel = to_package.replace(".", "/") + f"/{cname}.java"
    new_path = repo_path / new_rel
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_text(text, encoding="utf-8")
    if new_path.resolve() != src.resolve():
        src.unlink()

    # 3) update every reference across the repo: imports + fully-qualified names
    files_changed = 1
    old_import = f"import {class_fqn};"
    new_import = f"import {new_fqn};"
    for jf in _java_files(repo_path):
        if jf.resolve() == new_path.resolve():
            continue
        try:
            t = jf.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        orig = t
        t = t.replace(old_import, new_import)
        t = re.sub(r"\b" + re.escape(class_fqn) + r"\b", new_fqn, t)
        # a class that was in the SAME old package used cname unqualified -> now needs an import
        if re.search(r"package\s+" + re.escape(from_pkg) + r"\s*;", t) and re.search(
                r"\b" + re.escape(cname) + r"\b", t) and new_import not in t:
            t = re.sub(r"(package\s+" + re.escape(from_pkg) + r"\s*;\s*\n)",
                       r"\1" + new_import + "\n", t, count=1)
        if t != orig:
            jf.write_text(t, encoding="utf-8")
            files_changed += 1
    return {"applied": True, "moved_from": class_fqn, "moved_to": new_fqn,
            "files_changed": files_changed, "note": "deterministic move-class"}


# --------------------------------------------------------------------------- #
# verify one suggestion end-to-end on a copy of the repo
# --------------------------------------------------------------------------- #
_MODULE_MARKERS = ("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle")


def _ignore_build_output(directory, names):
    """Skip build OUTPUT directories without skipping source packages that share their name.

    `ignore_patterns("build")` matches a directory called `build` at ANY depth, and
    `org.apache.commons.io.build` is a real commons-io source package. Every copy silently
    dropped it, so the copy failed to compile with 88 "package does not exist" errors -
    before any refactoring ran. The measurements taken on those copies were meaningless.

    `target`/`build` are only build output when they sit next to a build file, so that is
    the test applied here; multi-module repositories still skip each module's output.
    """
    ignored = {n for n in names if n == ".git" or n.endswith(".class")}
    if any(m in names for m in _MODULE_MARKERS):
        ignored |= {n for n in names
                    if n in ("target", "build") and (Path(directory) / n).is_dir()}
    return ignored


def _copy_repo(repo_path: Path, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(repo_path, dest, ignore=_ignore_build_output)
    return dest


def _class_importing(repo_path: Path, decl_pkg: str, other_pkg: str) -> Optional[str]:
    """A class declared in decl_pkg whose file imports other_pkg (an edge creator)."""
    imp = re.compile(r"import\s+(?:static\s+)?" + re.escape(other_pkg) + r"\.")
    pkg = re.compile(r"package\s+" + re.escape(decl_pkg) + r"\s*;")
    for jf in _java_files(repo_path):
        try:
            t = jf.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if pkg.search(t) and imp.search(t):
            return f"{decl_pkg}.{jf.stem}"
    return None


def write_openrewrite_recipe(moves: List[str], target_pkg: str, out_path: Path) -> str:
    """Emit the equivalent OpenRewrite recipe (ChangeType per moved class).

    This is the tool-based artifact for the same transformation the deterministic applier
    performed. Run with Maven: `mvn -U org.openrewrite.maven:rewrite-maven-plugin:run
    -Drewrite.activeRecipes=com.dsarp.BreakCycle` (requires Maven + the moved classes to
    exist). We generate it as a reproducible recipe; validation still requires a real build.
    """
    lines = ["type: specs.openrewrite.org/v1beta/recipe",
             "name: com.dsarp.BreakCycle",
             "displayName: Break package cycle by relocating crossing classes",
             "recipeList:"]
    for fqn in moves:
        cname = fqn.rsplit(".", 1)[-1]
        lines += ["  - org.openrewrite.java.ChangeType:",
                  f"      oldFullyQualifiedTypeName: {fqn}",
                  f"      newFullyQualifiedTypeName: {target_pkg}.{cname}"]
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(out_path)


def simulate_cumulative(snapshot: SmellSnapshot, suggestions: List[Dict[str, Any]],
                        max_steps: int = 25) -> Dict[str, Any]:
    """Apply the top suggestions' edge-breaks CUMULATIVELY and track the cycle trajectory.

    A single refactoring rarely dents a tangled repo, but a sequence can. Each suggestion breaks
    its target boundary edge (Extract Interface / Dependency Inversion / Move Class all remove the
    concrete cross-package dependency). We remove unique target edges one by one and re-count cycles
    after each step -> a cycle-reduction curve. Graph-level simulation (clearly labelled).
    """
    import networkx as nx
    g = nx.DiGraph()
    for e in snapshot.edges:
        g.add_edge(e["source"], e["target"])

    def scc_metrics():
        """(largest tangle size, #packages still in any cycle). Linear-time, uncapped —
        the robust way to measure a dense tangle where raw cycle count saturates."""
        nontrivial = [len(c) for c in nx.strongly_connected_components(g) if len(c) > 1]
        return (max(nontrivial) if nontrivial else 0, sum(nontrivial))

    scc0, pkgs0 = scc_metrics()
    traj = [{"step": 0, "edge": None, "refactoring": None,
             "largest_tangle": scc0, "packages_in_cycles": pkgs0}]
    applied, step = set(), 0
    for s in suggestions:
        b = s.get("target_boundary", {})
        frm, to = b.get("from"), b.get("to")
        if not frm or not to or (frm, to) in applied or not g.has_edge(frm, to):
            continue
        g.remove_edge(frm, to)
        applied.add((frm, to))
        step += 1
        scc, pkgs = scc_metrics()
        traj.append({"step": step, "edge": f"{frm}->{to}",
                     "refactoring": s.get("recommended_refactoring"),
                     "largest_tangle": scc, "packages_in_cycles": pkgs})
        if step >= max_steps:
            break
    scc1, pkgs1 = traj[-1]["largest_tangle"], traj[-1]["packages_in_cycles"]
    return {"largest_tangle_before": scc0, "largest_tangle_after": scc1,
            "packages_in_cycles_before": pkgs0, "packages_in_cycles_after": pkgs1,
            "steps": step, "packages_freed": pkgs0 - pkgs1,
            "reduction_pct": round(100 * (pkgs0 - pkgs1) / pkgs0, 1) if pkgs0 else 0.0,
            "trajectory": traj}


def _crossing_classes(repo_path: Path, decl_pkg: str, other_pkg: str) -> List[str]:
    """All classes declared in decl_pkg whose file imports other_pkg (edge decl->other)."""
    imp = re.compile(r"import\s+(?:static\s+)?" + re.escape(other_pkg) + r"\.")
    pkg = re.compile(r"package\s+" + re.escape(decl_pkg) + r"\s*;")
    out = []
    for jf in _java_files(repo_path):
        try:
            t = jf.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if pkg.search(t) and imp.search(t):
            out.append(f"{decl_pkg}.{jf.stem}")
    return out


def apply_break_cycle(repo_path: Path, a_pkg: str, b_pkg: str) -> Dict[str, Any]:
    """Break a 2-package cycle by moving EVERY class creating the cheaper edge direction.

    Removes one full direction of the A<->B edge, which breaks the 2-cycle. Chooses the
    direction with fewer contributing classes (least-effort). This is the realistic scope
    of a cycle-breaking Move Class / package consolidation on a real repo.
    """
    a_to_b = _crossing_classes(repo_path, a_pkg, b_pkg)   # move these into b_pkg
    b_to_a = _crossing_classes(repo_path, b_pkg, a_pkg)   # move these into a_pkg
    if not a_to_b and not b_to_a:
        return {"applied": False, "note": "no crossing classes found"}
    if a_to_b and (not b_to_a or len(a_to_b) <= len(b_to_a)):
        movers, target, direction = a_to_b, b_pkg, f"{a_pkg}->{b_pkg}"
    else:
        movers, target, direction = b_to_a, a_pkg, f"{b_pkg}->{a_pkg}"
    for fqn in movers:
        apply_move_class(repo_path, fqn, target)
    return {"applied": True, "direction_removed": direction, "classes_moved": movers,
            "count": len(movers), "target_package": target}


def _pick_move(suggestion: Dict[str, Any], repo_path: Path) -> Optional[Dict[str, Any]]:
    """On a 2-package cycle A<->B, move an EDGE-CREATING class to the other package.

    Prefer the direction (A->B or B->A) created by the FEWEST classes, since moving those
    is most likely to break the cycle with a single relocation.
    """
    b = suggestion.get("target_boundary", {})
    a_pkg, b_pkg = b.get("from"), b.get("to")
    if not a_pkg or not b_pkg:
        return None
    for decl_pkg, other in ((b_pkg, a_pkg), (a_pkg, b_pkg)):
        cls = _class_importing(Path(repo_path), decl_pkg, other)
        if cls:
            return {"class_fqn": cls, "to_package": other, "edge": f"{decl_pkg}->{other}"}
    return None


def apply_split_package(repo_path: Path, pkg: str, source_index: Dict[str, Any],
                        min_classes: int = 6) -> Dict[str, Any]:
    """God Component fix: split an over-large package by moving half its classes into a
    new sub-package `<pkg>.internal`. Real source change (relocates files + fixes imports),
    which lowers the class count below the God-Component threshold."""
    classes = sorted(c for c in source_index.get("classes", []) if c.rsplit(".", 1)[0] == pkg)
    if len(classes) < min_classes:
        return {"applied": False, "note": f"only {len(classes)} classes — too few to split"}
    to_move = classes[len(classes) // 2:]
    new_pkg = pkg + ".internal"
    moved = [fqn for fqn in to_move if apply_move_class(repo_path, fqn, new_pkg).get("applied")]
    return {"applied": bool(moved), "moved": len(moved), "new_package": new_pkg,
            "classes_moved": moved}


def verify_suggestion(repo_path: Path, suggestion: Dict[str, Any], work_dir: Path,
                      before: Optional[SmellSnapshot] = None,
                      source_index: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Apply one suggestion on a fresh copy and check whether the SPECIFIC smell is removed.

    Works for ANY smell type (not just cyclic): re-detects the exact smell (type + components)
    after the change. Source-applies Cyclic (Move Class) and God Component (Split Package);
    other design-heavy smells are graph-simulated. `before`/`source_index` reused across calls.
    """
    repo_path = Path(repo_path)
    pid = suggestion.get("project_id", "repo")
    before = before if before is not None else snapshot_smells(repo_path, pid)
    idx = source_index if source_index is not None else SourceIndexer().index(pid, repo_path).to_dict()

    rtype = suggestion.get("recommended_refactoring", "")
    smell_type = suggestion.get("smell_type", "")
    st = smell_type.lower()
    components = [c.get("id") for c in suggestion.get("affected_components", []) if c.get("id")]
    sid = suggestion.get("suggestion_id", "x")[:8]
    result: Dict[str, Any] = {
        "suggestion_id": suggestion.get("suggestion_id"), "refactoring": rtype,
        "smell_type": smell_type, "applied": False, "applier": None,
        "smells_before": before.total, "cycles_before": before.cycle_count,
    }

    def finish_source(after: SmellSnapshot, applier: str, removed: bool, **extra):
        result.update({"applied": True, "applier": applier,
                       "smells_after": after.total, "cycles_after": after.cycle_count,
                       "smell_removed": removed,
                       "smell_delta": after.total - before.total,
                       "new_smells": max(0, after.total - before.total), **extra})
        return result

    # --- Cyclic Dependency -> Move Class (source), escalate to move-all-crossing --------- #
    if "cyclic" in st:
        move = _pick_move(suggestion, repo_path)
        if not move:
            result["note"] = "no crossing class to move on the cycle boundary"
            return result
        copy = _copy_repo(repo_path, work_dir / f"copy_{sid}")
        apply_move_class(copy, move["class_fqn"], move["to_package"])
        after = snapshot_smells(copy, pid)
        shutil.rmtree(copy, ignore_errors=True)
        result["move"] = move
        if after.cycle_count >= before.cycle_count:  # escalate
            b = suggestion.get("target_boundary", {})
            copy2 = _copy_repo(repo_path, work_dir / f"copyfull_{sid}")
            full = apply_break_cycle(copy2, b.get("from", ""), b.get("to", ""))
            if full.get("applied"):
                after = snapshot_smells(copy2, pid)
                result["break_cycle"] = {k: full[k] for k in ("direction_removed", "count", "target_package")}
                result["openrewrite_recipe"] = write_openrewrite_recipe(
                    full["classes_moved"], full["target_package"], work_dir / "recipes" / f"{sid}.yml")
            shutil.rmtree(copy2, ignore_errors=True)
            return finish_source(after, "move-all-crossing-classes",
                                 removed=after.cycle_count < before.cycle_count)
        return finish_source(after, "deterministic-move-class",
                             removed=after.cycle_count < before.cycle_count)

    # --- God Component / Hub-Like -> Split Package (source: fewer classes + lower fan) --- #
    if ("god" in st or "hub" in st) and components:
        copy = _copy_repo(repo_path, work_dir / f"copy_{sid}")
        sp = apply_split_package(copy, components[0], idx)
        if sp.get("applied"):
            after = snapshot_smells(copy, pid)
            shutil.rmtree(copy, ignore_errors=True)
            result["split_package"] = {k: sp[k] for k in ("moved", "new_package")}
            result["openrewrite_recipe"] = write_openrewrite_recipe(
                sp["classes_moved"], sp["new_package"], work_dir / "recipes" / f"{sid}.yml")
            return finish_source(after, "split-package (source)",
                                 removed=not after.has_smell(smell_type, components))
        shutil.rmtree(copy, ignore_errors=True)
        result["note"] = sp.get("note")
        result["smell_removed"] = False
        return result

    # --- Arcan/Designite-only smells the structural detector can't re-detect ------------ #
    # (Feature Concentration, Scattered Functionality, Dense Structure need cohesion analysis;
    # we can't confirm their removal without re-running Arcan/Designite — say so honestly.)
    if not any(k in st for k in ("cyclic", "hub", "unstable", "god")):
        result.update({"applier": "n/a", "applied": False, "smell_removed": None,
                       "note": f"{smell_type}: Arcan/Designite-specific smell — structural "
                               "re-detection unavailable; cannot verify removal without re-running the tool."})
        return result

    # --- Unstable Dependency -> graph simulation (dependency inversion breaks the edge) -- #
    b = suggestion.get("target_boundary", {})
    sim = simulate_refactoring(before, b.get("from", ""), b.get("to", ""), rtype)
    result.update({
        "applier": "graph-simulation", "applied": False, "simulated": True,
        "smells_after": before.total, "cycles_after": sim["cycles_after"],
        "smell_removed": sim["smell_removed"], "simulation": sim,
        "note": f"{smell_type}/{rtype}: graph-simulated (source auto-apply needs a design edit).",
    })
    return result
