"""Build and invoke the Spoon edit driver (tools/dsarp-spoon).

Kept separate from the OpenRewrite runner because they fail differently: OpenRewrite runs
inside the target's Maven build and dies on the target's dependency resolution, while Spoon
parses source with `setNoClasspath(true)` and does not care whether the repo builds. That is
the whole reason this path exists for large repos.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

MODULE = Path(__file__).resolve().parents[2] / "tools" / "dsarp-spoon"
JAR = MODULE / "target" / "dsarp-spoon-1.0.0.jar"


def java_exe() -> Optional[str]:
    if shutil.which("java"):
        return "java"
    from .arcan_runner import jdk_home_for
    home = jdk_home_for("17", "21", "11")
    return str(home / "bin" / "java.exe") if home else None


def driver_built() -> bool:
    return JAR.exists()


def build_driver(timeout: int = 900) -> Dict[str, Any]:
    """`mvn package` the driver. The Spoon version in the pom is verified by this build."""
    from ..openrewrite.runner import find_mvn, _build_env
    mvn = find_mvn()
    if not mvn:
        return {"ok": False, "status": "maven_not_found"}
    try:
        proc = subprocess.run([mvn, "-B", "-ntp", "-f", str(MODULE / "pom.xml"), "package"],
                              capture_output=True, text=True, timeout=timeout,
                              env=_build_env())
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "timeout"}
    ok = proc.returncode == 0 and JAR.exists()
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return {"ok": ok, "status": "built" if ok else "failed", "jar": str(JAR),
            "errors": [l.strip() for l in out.splitlines() if "[ERROR]" in l][:5],
            "tail": out[-2000:]}


def module_of(source_root: Path) -> Path:
    """The build module a source root belongs to — <module>/src/main/java -> <module>."""
    p = Path(source_root)
    for parent in [p, *p.parents]:
        if (parent / "pom.xml").exists():
            return parent
    return p


def module_classpath(repo_path: Path, source_root: Path,
                     timeout: int = 1800) -> Dict[str, Any]:
    """The module's compile classpath, from Maven.

    Spoon was run with `setNoClasspath(true)` throughout the previous work, which means it
    parsed source without resolving types. Every reference then had to be repaired by hand
    afterwards, and four separate classes of access error (missing imports, target-package
    imports, protected nested types, package-private types) were each discovered only by
    compiling the result. With a real classpath Spoon answers those questions itself.

    Requires the module's dependencies to be resolvable — the same precondition the build
    already has.
    """
    from ..openrewrite.runner import _build_env, find_mvn
    mvn = find_mvn()
    if not mvn:
        return {"ok": False, "status": "maven_not_found", "entries": []}
    module = module_of(source_root)
    out = Path(tempfile.mkdtemp(prefix="dsarp-cp-")) / "cp.txt"
    cmd = [mvn, "-B", "-ntp", "-q", "-f", str(module / "pom.xml"),
           "dependency:build-classpath", f"-Dmdep.outputFile={out}",
           # TEST scope, not compile: the precheck now models src/test/java so it can see a
           # test reading a package-private member of a type being moved out from under it.
           # Without junit and friends resolvable, that model build throws and the driver
           # falls back to the weaker main-only check on every single candidate.
           "-Dmdep.includeScope=test", "-DincludeScope=test",
           "-Dmaven.test.skip=true", "-Drat.skip=true", "-Denforcer.skip=true",
           "-Dcheckstyle.skip=true", "-Dlicense.skip=true", "-Danimal.sniffer.skip=true"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              env=_build_env())
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "classpath_timeout", "entries": []}
    if not out.exists():
        tail = ((proc.stdout or "") + (proc.stderr or ""))[-1200:]
        return {"ok": False, "status": "classpath_failed", "entries": [], "tail": tail}
    raw = out.read_text(encoding="utf-8", errors="ignore").strip()
    entries = [e for e in raw.split(os.pathsep) if e]
    # The module's own compiled classes, when present, resolve its sibling types.
    # Compiled classes resolve the module's own cross-file types. A working copy has none, so
    # take them from the original it was copied from: the sources are identical before the edit,
    # and Maven still compiles the copy without them. Missing this made precheck and apply
    # disagree -- tika's precheck ran on the original (58 entries) and called six moves legal,
    # apply ran on the copy (56) and died on "RTFTokenizer cannot be resolved to a type".
    from ..verification.effect_checker import original_module
    for tree in (module, original_module(module)):
        if tree is None:
            continue
        for sub in ("classes", "test-classes"):
            d = tree / "target" / sub
            if d.is_dir() and str(d) not in entries:
                entries.append(str(d))
    shutil.rmtree(out.parent, ignore_errors=True)
    return {"ok": bool(entries), "status": "resolved" if entries else "empty",
            "entries": entries, "module": str(module)}


def compliance_level(module: Path, timeout: int = 600) -> int:
    """The module's Java source level, from Maven.

    Spoon's JDT parser defaults to Java 8. Tika's tika-core failed to model at all with
    `Syntax error on token "implements", throws expected` — not a broken file, a parser set
    to an older language than the source is written in. Every candidate in the module then
    came back refused, for a reason that had nothing to do with the refactoring.
    """
    from ..openrewrite.runner import _build_env, find_mvn
    mvn = find_mvn()
    if not mvn:
        return 17
    for expr in ("maven.compiler.release", "maven.compiler.source", "java.version"):
        try:
            proc = subprocess.run(
                [mvn, "-B", "-ntp", "-q", "-f", str(module / "pom.xml"),
                 "help:evaluate", f"-Dexpression={expr}", "-DforceStdout"],
                capture_output=True, text=True, timeout=timeout, env=_build_env())
        except subprocess.TimeoutExpired:
            break
        val = (proc.stdout or "").strip().splitlines()
        val = val[-1].strip() if val else ""
        m = re.search(r"(?:1\.)?(\d+)", val)
        if m and val and "null object" not in val:
            n = int(m.group(1))
            if 5 <= n <= 25:
                return n
    return 17


_IMPORT = "import {};"


def fix_references(repo_path: Path, moves: List[Dict[str, str]]) -> Dict[str, Any]:
    """Repoint every reference to a moved type. Text, not AST, and deliberately so.

    Spoon reparents the CtType and its auto-import was supposed to reprint the imports. On a
    three-class test repo it did; on log4j-core it did not, and the build failed with
    `cannot find symbol: class Appender, location: package org.apache.logging.log4j.core` —
    the exact class we had just moved out of that package. Rather than fight the printer,
    the moved FILE comes from Spoon (it needs real imports for its former siblings) and the
    references to it are rewritten here, where the rule is three lines and testable:

      * `import old.pkg.Simple;`   -> `import new.pkg.Simple;`
      * fully-qualified `old.pkg.Simple` -> `new.pkg.Simple`
      * a file LEFT BEHIND in old.pkg used `Simple` with no import, because it used to be a
        sibling. It now needs one. This is the case that broke the build.
    # ponytail: textual, so it will not see `Simple` inside a string or comment
    """
    touched, added = [], 0
    files = [f for f in Path(repo_path).rglob("*.java")
             if "/target/" not in str(f).replace("\\", "/")]
    for f in files:
        try:
            txt = original = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        pkg_m = re.search(r"^\s*package\s+([\w.]+)\s*;", txt, re.M)
        this_pkg = pkg_m.group(1) if pkg_m else ""
        for mv in moves:
            old_fqn, new_pkg = mv["type"], mv["toPackage"]
            simple = old_fqn.rsplit(".", 1)[-1]
            old_pkg = old_fqn.rsplit(".", 1)[0]
            new_fqn = f"{new_pkg}.{simple}"
            # A file in the TARGET package still needs its stale import rewritten. Skipping
            # those was the bug: Configuration.java sits in core.config, Appender moved INTO
            # core.config, and its `import ...core.Appender;` was left pointing at a class
            # that no longer exists there. Only the moved file itself is exempt.
            if f == Path(mv.get("newPath", "")) or f.name == f"{simple}.java" and this_pkg == new_pkg:
                continue
            if this_pkg == new_pkg:
                # The type has moved INTO this file's own package, so the import is now
                # same-package. Java allows that; pdfbox's checkstyle does not, and the
                # build failed with four RedundantImport errors on code javac had accepted.
                drop = {_IMPORT.format(old_fqn), _IMPORT.format(new_fqn)}
                txt = "".join(ln for ln in txt.splitlines(keepends=True)
                              if ln.strip() not in drop)
            else:
                txt = txt.replace(_IMPORT.format(old_fqn), _IMPORT.format(new_fqn))
            txt = re.sub(rf"\b{re.escape(old_fqn)}\b", new_fqn, txt)
            # Left behind in the old package and still using the bare name.
            # Searched in CODE, not text. pdfbox's CompoundCharacterTokenizer only named the moved
            # class in a comment, gained an import it never used, and checkstyle failed the build:
            # a refactoring scored as broken over a comment.
            if (this_pkg == old_pkg and _IMPORT.format(new_fqn) not in txt
                    and re.search(rf"\b{re.escape(simple)}\b",
                                  re.sub(r"//[^\n]*|/\*.*?\*/", "", txt, flags=re.S))):
                txt = re.sub(r"^(\s*package\s+[\w.]+\s*;\s*\n)",
                             rf"\1\n{_IMPORT.format(new_fqn)}\n", txt, count=1, flags=re.M)
                added += 1
        if txt != original:
            f.write_text(txt, encoding="utf-8")
            touched.append(str(f))
    return {"files_rewritten": len(touched), "imports_added": added}


# Import hygiene is shared with the OpenRewrite arm; refactoring/java_text.py carries
# the reasoning, including why nothing in it uses a regex.
from ..refactoring.java_text import idents as _idents
from ..refactoring.java_text import strip_unused_imports as _strip_unused_imports


def _install_moved_files(repo_path: Path, applied: List[Dict[str, str]]) -> Dict[str, Any]:
    """Copy each moved type out of Spoon's scratch output into its new package directory."""
    installed, missing, pruned = [], [], {}
    for a in applied:
        # extractInterface writes rather than moves: one new interface file plus the
        # implementation and every consumer whose references were retargeted. The driver
        # reports the exact scratch -> repo pairs, so nothing is inferred and nothing is
        # deleted.
        if a.get("op") in ("extractInterface", "invertEdge"):
            from ..refactoring.java_text import add_implements, retarget_type
            # invertEdge abstracts several classes at once, so the impl -> interface mapping
            # is a list; extractInterface is the one-pair case of the same thing.
            pairs = a.get("pairs") or [{"type": a.get("type", ""),
                                        "interfaceFqn": a.get("interfaceFqn", "")}]
            by_simple = {p["type"].rsplit(".", 1)[-1]: p for p in pairs if p.get("type")}
            iface_fqn = a.get("interfaceFqn", "")
            impl_fqn = a.get("type", "")
            for w in (a.get("writes") or []):
                src, dst = Path(w.get("from", "")), Path(w.get("to", ""))
                kind = w.get("kind")
                if kind == "interface":
                    # New file: nothing to preserve, so take the printer's output.
                    if not src.exists():
                        missing.append(w.get("from"))
                        continue
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    txt, dropped = _strip_unused_imports(
                        src.read_text(encoding="utf-8", errors="ignore"))
                    dst.write_text(txt, encoding="utf-8")
                    if dropped:
                        pruned[str(dst)] = dropped
                    installed.append(str(dst))
                    continue
                # Existing files are patched IN PLACE. Taking the printer's copy reformats
                # the whole file, and pdfbox failed two candidates on a 278-character line
                # with no javac error at all.
                if not dst.exists():
                    missing.append(w.get("to"))
                    continue
                original = dst.read_text(encoding="utf-8", errors="ignore")
                if kind == "impl":
                    simple = w.get("simpleName", "")
                    want = w.get("interfaceFqn") or by_simple.get(simple, {}).get(
                        "interfaceFqn", iface_fqn)
                    txt, ok = add_implements(original, simple, want)
                    if not ok:
                        missing.append("could not add implements to " + str(dst))
                        continue
                else:
                    # A consumer may name several of the inverted classes; retarget each.
                    txt = original
                    for pr in pairs:
                        txt = retarget_type(txt, pr["type"], pr["interfaceFqn"])
                if txt != original:
                    dst.write_text(txt, encoding="utf-8")
                    installed.append(str(dst))
            continue
        new_src = Path(a.get("newPath", ""))
        simple = a["type"].rsplit(".", 1)[-1]
        dest = (Path(a["root"]) / a["toPackage"].replace(".", "/") / f"{simple}.java")
        if not new_src.exists():
            missing.append(a["type"])
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        txt, dropped = _strip_unused_imports(
            new_src.read_text(encoding="utf-8", errors="ignore"))
        dest.write_text(txt, encoding="utf-8")
        if dropped:
            pruned[str(dest)] = dropped
        installed.append(str(dest))
        old = Path(a.get("oldPath", ""))
        if old.exists() and old.resolve() != dest.resolve():
            old.unlink()          # a stale duplicate would be a compile error on its own
    return {"installed": installed, "missing_output": missing,
            "unused_imports_pruned": pruned}


def apply_edits(repo_path: Path, edits: List[Dict[str, str]],
                source_roots: Optional[List[str]] = None,
                heap: str = "-Xmx4g", timeout: int = 1800,
                log_path: Optional[Path] = None,
                classpath: Optional[List[str]] = None,
                resolve_types: bool = True, mode: str = "apply",
                conservative: bool = False) -> Dict[str, Any]:
    """Apply a validated edit plan to `repo_path` in place. Caller supplies a COPY."""
    if not driver_built():
        return {"ok": False, "status": "driver_not_built",
                "note": "run: mvn -f tools/dsarp-spoon/pom.xml package"}
    java = java_exe()
    if not java:
        return {"ok": False, "status": "java_not_found"}
    if not edits:
        return {"ok": True, "status": "no_edits", "applied": [], "skipped": []}

    tmp = Path(tempfile.mkdtemp(prefix="dsarp-spoon-"))
    plan_file, result_file = tmp / "plan.json", tmp / "result.json"
    scratch = tmp / "out"
    # Derive the module classpath unless one was supplied. Without it Spoon parses source
    # with no type resolution, which is what forced every access question to be answered by
    # compiling the result instead of by asking the model.
    cp_report = None
    if classpath is None and resolve_types and source_roots:
        cp_report = module_classpath(Path(repo_path), Path(repo_path) / source_roots[0])
        classpath = cp_report.get("entries") or []
    level = compliance_level(module_of(Path(repo_path) / source_roots[0])) if source_roots else 17
    plan_file.write_text(json.dumps({"edits": edits, "sourceRoots": source_roots or [],
                                     "outputDir": str(scratch), "mode": mode,
                                     "conservative": conservative,
                                     "complianceLevel": level,
                                     "classpath": classpath or []}), encoding="utf-8")
    cmd = [java, heap, "-jar", str(JAR), str(repo_path), str(plan_file), str(result_file)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              env=dict(os.environ))
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "timeout", "note": f"exceeded {timeout}s"}
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text(out, encoding="utf-8")
    if not result_file.exists():
        return {"ok": False, "status": "failed", "returncode": proc.returncode,
                "tail": out[-2000:]}
    result = json.loads(result_file.read_text(encoding="utf-8"))
    if result.get("mode") == "precheck":
        # Nothing was written; "applied" carries the legal set and "skipped" the refusals.
        result["legal"] = result.pop("applied", [])
        result["illegal"] = result.pop("skipped", [])
        result["status"] = "prechecked"
        shutil.rmtree(tmp, ignore_errors=True)
        return result
    if cp_report is not None:
        result["classpath"] = {k: cp_report.get(k) for k in ("ok", "status", "module")}
        result["classpath"]["entries"] = len(cp_report.get("entries") or [])
    applied = result.get("applied") or []
    if applied:
        # Spoon printed a whole rewritten source root into scratch. Take ONLY the files that
        # moved; every other file it touched is collateral we do not want.
        result["install"] = _install_moved_files(Path(repo_path), applied)
        # Reference repair is for MOVES. An extracted interface relocates nothing, and Spoon
        # retargeted the consumers in-model, so running the textual pass over it would only
        # find a type that never changed package.
        moves = [a for a in applied
                 if a.get("op") not in ("extractInterface", "invertEdge")]
        if moves:
            result["references"] = fix_references(Path(repo_path), moves)
    result["status"] = "changed" if applied else "no_change"
    result["returncode"] = proc.returncode
    result["tail"] = out[-2000:]
    shutil.rmtree(tmp, ignore_errors=True)
    return result


def precheck_edits(repo_path: Path, edits: List[Dict[str, str]],
                   source_roots: Optional[List[str]] = None,
                   classpath: Optional[List[str]] = None,
                   timeout: int = 1800,
                   log_path: Optional[Path] = None,
                   conservative: bool = False) -> Dict[str, Any]:
    """Which of these moves are legal, according to the resolved model. Changes nothing.

    Enumeration in Python matches source with regexes, so it cannot see package-private
    field access. On pdfbox it offered ten candidates, the agent spent ten calls choosing
    among them, and the driver then refused all ten — every model call wasted on a move that
    was never applicable. Deciding legality first means the agent only ever chooses between
    moves that can actually be applied.
    """
    return apply_edits(repo_path, edits, source_roots=source_roots, classpath=classpath,
                       timeout=timeout, log_path=log_path, mode="precheck",
                       conservative=conservative)


def precheck_by_module(repo_path: Path, edits: List[Dict[str, str]], facts,
                       log_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Precheck each candidate inside its OWN module, with that module's classpath.

    One classpath for the whole run is wrong on a multi-module repository: Spoon resolves
    the module it was given and every candidate living elsewhere comes back "type not found
    in any source root". That is not an access refusal, it is a modelling gap — it made tika
    report 0 legal of 17 while every single refusal was this message.
    """
    from ..refactoring import spoon_plan

    by_root: Dict[str, List[Dict[str, str]]] = {}
    unresolved = []
    for e in edits:
        root = spoon_plan.source_root_of(facts, e["type"])
        if root is None:
            unresolved.append({"edit": e, "why": "no source root for this type"})
            continue
        by_root.setdefault(str(root), []).append(e)

    legal, illegal, modules = [], list(unresolved), {}
    for root, group in by_root.items():
        cp = module_classpath(Path(repo_path), Path(root))
        modules[module_of(Path(root)).name] = {
            "status": cp.get("status"), "entries": len(cp.get("entries") or []),
            "candidates": len(group),
        }
        if not cp.get("entries"):
            # No classpath means no access checking; refusing beats guessing.
            illegal += [{"edit": e, "why": f"no classpath for module "
                                           f"{module_of(Path(root)).name} ({cp.get('status')})",
                         "companions": []} for e in group]
            continue
        rel = str(Path(root).relative_to(repo_path))
        res = precheck_edits(repo_path, group, source_roots=[rel],
                             classpath=cp["entries"],
                             log_path=(Path(log_dir) / f"precheck_{module_of(Path(root)).name}.log")
                             if log_dir else None)
        legal += res.get("legal") or []
        illegal += res.get("illegal") or []
    return {"legal": legal, "illegal": illegal, "modules": modules,
            "status": "prechecked"}
