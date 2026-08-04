"""Execute the REAL Arcan 1.2.1 architectural smell detector.

Arcan analyses **compiled bytecode**, not .java source, so a run is two stages:

    1. compile   `mvn compile` (or reuse an existing target/classes)  -> .class files
    2. detect    `java -jar arcan-1.2.1.jar -p <classes> -out <dir> -all`

Arcan writes CSVs into <out>; `smell-characteristics.csv` carries one row per smell
instance (smellType / AffectedElements / Severity / ATDI), which the existing
`ArcanAdapter` already parses.

The distribution must be the FULL one (jar + lib/, 121 jars) — the bare arcan-1.2.1.jar
is a thin jar and dies with NoClassDefFoundError tinkerpop/gremlin. `arcan_home()`
therefore looks for a directory that contains BOTH the jar and lib/.

Nothing here fabricates findings: if compile or detect fails, the status says so and the
finding list is empty.
"""
from __future__ import annotations

import collections
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .arcan import ArcanAdapter

# Smell types Arcan 1.2.1 can detect, and the flag that enables all of them.
ARCAN_SMELLS = ("Cyclic Dependency", "Hub-Like Dependency", "Unstable Dependency")


def _tools_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "tools"


def arcan_home() -> Optional[Path]:
    """Directory holding a RUNNABLE Arcan: needs arcan-*.jar next to a non-empty lib/."""
    for jar in sorted(_tools_dir().rglob("arcan-*.jar")):
        if jar.name.endswith("-sources.jar"):
            continue
        lib = jar.parent / "lib"
        if lib.is_dir() and any(lib.glob("*.jar")):
            return jar.parent
    return None


def arcan_jar() -> Optional[Path]:
    home = arcan_home()
    if not home:
        return None
    jars = [j for j in home.glob("arcan-*.jar") if not j.name.endswith("-sources.jar")]
    return jars[0] if jars else None


def find_mvn() -> Optional[str]:
    """Reuse the OpenRewrite runner's Maven discovery (PATH or bundled tools/)."""
    from ..openrewrite.runner import find_mvn as _f
    return _f()


def compile_repo(repo_path: Path, timeout: int = 2400,
                 log_path: Optional[Path] = None) -> Dict[str, Any]:
    """`mvn compile` so Arcan has bytecode. Returns status + the class dirs produced."""
    repo_path = Path(repo_path)
    existing = _class_dirs(repo_path)
    mvn = find_mvn()
    if not mvn:
        if existing:
            return {"ok": True, "status": "reused_existing_classes",
                    "class_dirs": [str(d) for d in existing]}
        return {"ok": False, "status": "maven_not_found",
                "note": "Arcan needs compiled classes; Maven not found."}
    pom = repo_path / "pom.xml"
    if not pom.exists():
        if existing:
            return {"ok": True, "status": "reused_existing_classes",
                    "class_dirs": [str(d) for d in existing]}
        # No pom, but Gradle can still produce the bytecode Arcan needs. Detection works
        # on Gradle projects even though OpenRewrite's maven plugin cannot refactor them.
        from ..verification.openrewrite_loop import detect_build_system
        if detect_build_system(repo_path) == "gradle":
            return compile_gradle(repo_path, timeout=timeout, log_path=log_path)
        return {"ok": False, "status": "no_pom",
                "class_dirs": [],
                "note": "No pom.xml or Gradle build, cannot compile for Arcan."}
    skips = ["-Drat.skip=true", "-Dcheckstyle.skip=true", "-Denforcer.skip=true",
             "-Dmaven.test.skip=true", "-Dspotless.check.skip=true", "-Dspotbugs.skip=true",
             "-Dpmd.skip=true", "-Danimal.sniffer.skip=true", "-Dlicense.skip=true",
             "-Djacoco.skip=true", "-Dmaven.javadoc.skip=true"]
    cmd = [mvn, "-B", "-ntp", "-f", str(pom), "compile", *skips]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "compile_timeout", "note": f"exceeded {timeout}s"}
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text(out, encoding="utf-8")
    dirs = _class_dirs(repo_path)
    ok = proc.returncode == 0 and bool(dirs)
    return {"ok": ok,
            "status": "compiled" if ok else ("compiled_no_classes" if proc.returncode == 0
                                             else "compile_failed"),
            "class_dirs": [str(d) for d in dirs], "returncode": proc.returncode,
            "command": " ".join(cmd), "tail": out[-2000:]}


def _class_dirs(repo_path: Path) -> List[Path]:
    """Compiled-output directories holding .class files, Maven or Gradle."""
    out = []
    # Maven: target/classes   Gradle: build/classes/java/main
    for pattern in ("target/classes", "build/classes/java/main"):
        for d in sorted(Path(repo_path).rglob(pattern)):
            if d.is_dir() and next(d.rglob("*.class"), None) is not None:
                out.append(d)
    return out


def gradle_wrapper(repo_path: Path) -> Optional[str]:
    """The project's own Gradle wrapper, which pins the version the build expects."""
    import os
    name = "gradlew.bat" if os.name == "nt" else "gradlew"
    w = Path(repo_path) / name
    return str(w) if w.exists() else (shutil.which("gradle") or None)


def compile_gradle(repo_path: Path, timeout: int = 2400,
                   log_path: Optional[Path] = None) -> Dict[str, Any]:
    """`gradlew classes` so Arcan has bytecode for a Gradle project.

    Arcan reads .class files and does not care which build tool produced them, so a Gradle
    project can be fully DETECTED even though OpenRewrite's maven plugin cannot refactor it.
    """
    repo_path = Path(repo_path)
    gw = gradle_wrapper(repo_path)
    if not gw:
        return {"ok": False, "status": "gradle_not_found",
                "note": "No gradlew wrapper and no gradle on PATH."}
    cmd = [gw, "classes", "--no-daemon", "-q",
           "-x", "test", "--console=plain"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              cwd=str(repo_path))
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"ok": False, "status": "compile_timeout", "note": str(e)[:200]}
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text(out, encoding="utf-8")
    dirs = _class_dirs(repo_path)
    ok = bool(dirs)
    return {"ok": ok, "status": "compiled" if ok else "compile_failed",
            "class_dirs": [str(d) for d in dirs], "returncode": proc.returncode,
            "build_tool": "gradle", "command": " ".join(cmd), "tail": out[-2000:]}


def run_arcan(classes_dir: Path, out_dir: Path, timeout: int = 2400,
              log_path: Optional[Path] = None) -> Dict[str, Any]:
    """Run Arcan on a folder of compiled classes; parse smell-characteristics.csv."""
    jar = arcan_jar()
    if not jar:
        return {"ok": False, "status": "arcan_not_found",
                "note": "Need the FULL Arcan distribution (jar + lib/)."}
    out_dir = Path(out_dir)
    # Start from a clean directory so a previous run's CSVs can never be re-parsed as if
    # they were this run's results.
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["java", "-jar", str(jar), "-p", str(Path(classes_dir).resolve()),
           "-out", str(out_dir.resolve()), "-all"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              cwd=str(jar.parent))
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "timeout", "note": f"exceeded {timeout}s"}
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text(out, encoding="utf-8")
    # Arcan 1.2.1 writes cycle-membership matrices + UD/HL tables (NOT smell-characteristics.csv);
    # the adapter's directory dispatch detects the schema and picks the right parser.
    findings = ArcanAdapter().import_findings(out_dir)
    counts = collections.Counter(f.smell_type for f in findings)
    ok = proc.returncode == 0
    return {"ok": ok, "status": "ok" if ok else "failed",
            "smells": len(findings), "by_type": dict(counts),
            "findings": [{"smell_type": f.smell_type, "components": f.affected_components,
                          "component_level": f.component_level, "severity": f.severity}
                         for f in findings],
            "out_dir": str(out_dir), "command": " ".join(cmd), "returncode": proc.returncode,
            "tail": out[-1500:]}


def detect_with_arcan(repo_path: Path, out_dir: Path, compile_log: Optional[Path] = None,
                      arcan_log: Optional[Path] = None) -> Dict[str, Any]:
    """Compile + Arcan in one call. Merges every module's classes into one result."""
    comp = compile_repo(repo_path, log_path=compile_log)
    dirs = [Path(d) for d in comp.get("class_dirs", [])]
    if not dirs:
        # No bytecode => Arcan CANNOT measure. "0 smells" here would be a false clean
        # bill of health, so the result is explicitly marked unmeasured.
        return {"ok": False, "status": comp["status"], "compile": comp, "measured": False,
                "smells": None, "by_type": {}, "findings": [],
                "note": "Arcan needs compiled bytecode; the build did not produce classes "
                        f"({comp['status']}). Smell counts are UNMEASURABLE, not zero."}
    findings: List[Dict[str, Any]] = []
    runs = []
    for i, d in enumerate(dirs):
        sub = Path(out_dir) / (f"module_{i}" if len(dirs) > 1 else "arcan")
        r = run_arcan(d, sub, log_path=(arcan_log if i == 0 else None))
        runs.append({"classes": str(d), "status": r["status"], "smells": r.get("smells", 0)})
        findings.extend(r.get("findings", []))
    counts = collections.Counter(f["smell_type"] for f in findings)
    measured = any(r["status"] == "ok" for r in runs)
    return {"ok": measured, "status": "ok" if measured else "failed", "measured": measured,
            "smells": len(findings) if measured else None,
            "by_type": dict(counts), "findings": findings,
            "compile": {k: v for k, v in comp.items() if k != "tail"},
            "modules": runs, "tool": "Arcan 1.2.1"}
