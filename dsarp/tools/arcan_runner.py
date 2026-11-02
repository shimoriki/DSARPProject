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
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from xml.etree import ElementTree

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


# A build can fail for reasons that have nothing to do with the source: a plugin goal that
# needs packaged jars simply cannot run under `compile`. Telling that apart from a real
# breakage is what separates "the refactoring broke this" from "this command was never
# going to work on this repository".
#
# Karaf hits two of these at once: maven-dependency-plugin:copy wants its siblings as jars
# (MDEP-187), and the reactor builds karaf-maven-plugin and then USES it, which needs the
# plugin descriptor that only `package` generates. Both are properties of the reactor, not
# of anything a refactoring did.
_NEEDS_PACKAGING_RE = re.compile(
    r"has not been packaged yet|MDEP-187|should be executed after packaging"
    r"|Failed to parse plugin descriptor|PluginDescriptorParsingException"
    r"|Could not find artifact \S+:jar:tests", re.I)

# Tika and Spark depend on their SIBLINGS' test-jars. Those are built by the test-jar goal
# during `package`, from test classes - so escalating while `-Dmaven.test.skip=true` is set
# produces no test-jar and the resolution fails exactly as before. Test sources have to be
# compiled; only RUNNING them is skipped, which `-DskipTests` already does.
_TEST_JAR_RE = re.compile(r"Could not find artifact \S+:jar:tests", re.I)

# "package x.y.z does not exist" / "cannot find symbol" against a THIRD-PARTY package means
# the module's dependencies are unobtainable here, not that its source is wrong.
_FAILED_MODULE_RE = re.compile(r"Failed to execute goal.*? on project ([\w.\-]+)", re.S)
_MISSING_EXTERNAL_RE = re.compile(
    r"package [\w.]+ does not exist|Could not resolve dependencies|Could not find artifact")


def _unbuildable_module(out: str):
    """The artifactId of a module that failed for want of a dependency, if any."""
    if not _MISSING_EXTERNAL_RE.search(out):
        return None
    m = _FAILED_MODULE_RE.search(out)
    return m.group(1) if m else None


def compile_repo(repo_path: Path, timeout: int = 2400,
                 log_path: Optional[Path] = None, goal: str = "compile") -> Dict[str, Any]:
    """`mvn compile` so Arcan has bytecode. Returns status + the class dirs produced.

    `goal="test-compile"` also builds the test sources without running them. Detection only
    needs main classes, but a VERDICT needs more: `compile` skips test compilation, so a move
    that leaves forty test files importing a class that is no longer there still reports
    `compiled`, and the break only surfaces if the candidate got far enough to run tests --
    which only the candidates that already looked good ever did.
    """
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
    # `maven.test.skip` skips COMPILING the tests, which is the point for detection and
    # exactly wrong for a verdict; `skipTests` compiles them and does not run them.
    skips = ["-Drat.skip=true", "-Dcheckstyle.skip=true", "-Denforcer.skip=true",
             "-Dmaven.test.skip=true" if goal == "compile" else "-DskipTests=true",
             "-Dspotless.check.skip=true", "-Dspotbugs.skip=true",
             "-Dpmd.skip=true", "-Danimal.sniffer.skip=true", "-Dlicense.skip=true",
             "-Djacoco.skip=true", "-Dmaven.javadoc.skip=true"]
    # A submodule of a multi-module build cannot compile standalone — its siblings are not
    # installed, so Maven reports "Could not resolve dependencies". Build it INSIDE the
    # reactor instead: `-f <root>/pom.xml -pl <module> -am` also builds what it depends on.
    reactor = _reactor_root(repo_path)
    if reactor is not None:
        rel = repo_path.resolve().relative_to(reactor.resolve()).as_posix()
        cmd = [mvn, "-B", "-ntp", "-f", str(reactor / "pom.xml"),
               "-pl", rel, "-am", goal, *skips]
    else:
        cmd = [mvn, "-B", "-ntp", "-f", str(pom), goal, *skips]
    excluded: list = []

    def _run(c):
        p = subprocess.run(c, capture_output=True, text=True, timeout=timeout)
        return p, (p.stdout or "") + "\n" + (p.stderr or "")

    try:
        proc, out = _run(cmd)
        # Karaf's reactor binds maven-dependency-plugin:copy to a phase that needs its
        # siblings PACKAGED as jars. Under `compile` they are still target/classes
        # directories, so the goal fails with MDEP-187 and the whole build reports FAILURE —
        # before any refactoring is applied. That made Karaf look permanently broken, and
        # every pass was rolled back for a reason that had nothing to do with the changes.
        # Arcan only needs bytecode, which `compile` already produced, so the packaging-only
        # goal is skipped and the build retried once.
        if proc.returncode != 0 and _NEEDS_PACKAGING_RE.search(out):
            # `compile` is the cheap goal and works for almost every repository, so it stays
            # the default. When the reactor demands real jars, the only correct answer is to
            # produce them - skipping the offending goal is not enough, because a self-hosted
            # plugin still has no descriptor. Escalate once, to `package`.
            cmd = [c if c != goal else "package" for c in cmd] + ["-DskipTests"]
            if _TEST_JAR_RE.search(out):
                # a sibling's test-jar cannot be built from test sources that were skipped
                cmd = [c for c in cmd if c != "-Dmaven.test.skip=true"]
            proc, out = _run(cmd)

        # A module can need a third-party artifact this machine cannot obtain - Struts' tiles
        # plugin wants org.apache.velocity.tools, which no goal produces. Installing it by
        # hand does not generalise: an unseen repository is cloned and built once, with
        # whatever its poms can actually resolve. Such modules are dropped from the reactor so
        # the rest can still be measured, and the exclusions are RECORDED, because a delta is
        # only meaningful when both sides excluded the same set.
        for _ in range(6):   # a large reactor can hide several unobtainable modules
            if proc.returncode == 0:
                break
            art = _unbuildable_module(out)
            if not art or art in excluded:
                break
            excluded.append(art)
            # Maven honours only the LAST -pl, so appending one per round silently
            # re-included everything excluded before it and the retry never converged.
            # Rebuild a single selector carrying every exclusion found so far.
            sel = ",".join("!:" + a for a in excluded)
            if "-pl" in cmd:
                # keep any existing selector (a reactor submodule build) and add to it,
                # replacing the VALUE rather than dropping the flag and orphaning it
                k = cmd.index("-pl")
                keep = [x for x in cmd[k + 1].split(",") if not x.startswith("!:")]
                cmd[k + 1] = ",".join([*keep, sel]) if keep else sel
            else:
                cmd += ["-pl", sel, "-am"]
            proc, out = _run(cmd)
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "compile_timeout", "note": f"exceeded {timeout}s"}
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text(out, encoding="utf-8")
    dirs = _class_dirs(repo_path)
    ok = proc.returncode == 0 and bool(dirs)
    return {"ok": ok,
            "status": "compiled" if ok else _failure_kind(out, proc.returncode),
            "class_dirs": [str(d) for d in dirs], "returncode": proc.returncode,
            "excluded_modules": excluded, "javac_errors": _javac_errors(out)[:5],
            "command": " ".join(cmd), "tail": out[-2000:]}


# Real compilation errors — the source does not compile.
_JAVAC_ERR = re.compile(r"\[ERROR\].*\.java:\[\d+,\d+\]|cannot find symbol|"
                        r"incompatible types|package \S+ does not exist", re.I)
# The build never got as far as compiling anything.
_QUALITY_GATE = re.compile(
    r"maven-(?:checkstyle|pmd|spotbugs|enforcer|rat|spotless|forbiddenapis)-plugin",
    re.I)
_RESOLUTION_ERR = re.compile(r"Could not resolve dependencies|Could not find artifact|"
                             r"Non-resolvable|Failed to collect dependencies", re.I)


def _javac_errors(out: str) -> List[str]:
    return [ln.strip() for ln in out.splitlines() if _JAVAC_ERR.search(ln)]


def _failure_kind(out: str, returncode: int) -> str:
    """Tell "our change broke the code" apart from "this build was already broken".

    log4j2's reactor wants log4j-fuzz-test:2.27.0-SNAPSHOT, which is not in the local
    repository (only 2.26.0 is). That failure is unrelated to any refactoring, produces ZERO
    javac errors, and was being reported as `compile_failed` — so an entire model sweep came
    back `rejected_build_broken` and looked like seven models writing bad code. A refactoring
    gate that cannot make this distinction manufactures false negatives.
    """
    if returncode == 0:
        return "compiled_no_classes"
    # 0xC0000142 on Windows: the JVM could not initialise, usually out of memory. No output.
    if returncode == 3221225794 or (not out.strip() and returncode != 0):
        return "jvm_start_failed"
    if _javac_errors(out):
        return "compile_failed"
    # A style gate is not a compilation failure. pdfbox's checkstyle rejected four
    # RedundantImport warnings on code javac had already accepted, and reporting that as
    # `compile_failed` blames the refactoring for breaking a build that in fact built.
    if _QUALITY_GATE.search(out):
        return "quality_gate_failed"
    if _RESOLUTION_ERR.search(out):
        return "dependency_unresolved"
    return "compile_failed"


def _reactor_root(module_path: Path) -> Optional[Path]:
    """The multi-module root whose pom lists this directory as a <module>, if any.

    Returns None for a standalone project, so ordinary single-repo runs are unaffected.
    """
    module_path = Path(module_path).resolve()
    parent = module_path.parent
    for _ in range(3):                      # modules nest at most a couple of levels deep
        pom = parent / "pom.xml"
        if pom.exists():
            try:
                text = pom.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                return None
            if f"<module>{module_path.name}</module>" in text.replace(" ", "") or \
                    f"<module>{module_path.name}</module>" in text:
                return parent
        if parent.parent == parent:
            break
        parent = parent.parent
    return None


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
    # Gradle supports a window of JDKs. Prefer 21 (current LTS, supported by every Gradle
    # this project meets), then 17; never 26 or 8, which Gradle rejects outright.
    env = dict(os.environ)
    jdk = jdk_home_for("21", "17")
    if jdk:
        env["JAVA_HOME"] = str(jdk)
        cmd.append(f"-Dorg.gradle.java.home={jdk}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              cwd=str(repo_path), env=env)
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"ok": False, "status": "compile_timeout", "note": str(e)[:200]}
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text(out, encoding="utf-8")
    dirs = _class_dirs(repo_path)
    ok = bool(dirs)
    status = "compiled" if ok else "compile_failed"
    note = None
    # Gradle builds pin a JDK range and refuse anything outside it. Reporting that as a
    # generic "compile_failed" hid an entirely fixable environment problem behind what
    # looked like a DSARP bug, so the requirement and the installed JDKs are surfaced.
    m = re.search(r"java version must be between (\d+) and (\d+)"
                  r"[^\n]*?your version:\s*(\d+)", out)
    if m and not ok:
        lo, hi, got = m.group(1), m.group(2), m.group(3)
        status = "jdk_version_unsupported"
        note = (f"This Gradle build requires JDK {lo}-{hi}; gradlew resolved JDK {got} "
                f"(JAVA_HOME={os.environ.get('JAVA_HOME', 'unset')}). Installed: "
                f"{', '.join(installed_jdks()) or 'none found'}. Set JAVA_HOME to a JDK in "
                f"range and re-run; nothing in DSARP needs to change.")
    return {"ok": ok, "status": status, "note": note,
            "class_dirs": [str(d) for d in dirs], "returncode": proc.returncode,
            "build_tool": "gradle", "command": " ".join(cmd), "tail": out[-2000:]}


def installed_jdks() -> List[str]:
    """JDKs discoverable on this machine, so a version mismatch names the alternatives."""
    roots = [Path(r"C:/Program Files/Java"), Path(r"C:/Program Files/Eclipse Adoptium"),
             Path.home() / ".jdks",
             # user-scope installs (the JetBrains/Oracle installers default here)
             Path.home() / "AppData/Local/Programs/Java",
             Path(r"C:/Program Files/Microsoft"), Path(r"C:/Program Files/Amazon Corretto"),
             Path(r"C:/Program Files/Zulu")]
    found = []
    for root in roots:
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if d.is_dir() and (d / "bin" / "javac.exe").exists():
                found.append(d.name)
    return found


def jdk_home_for(*versions: str):
    """Absolute path of the first installed JDK whose name matches one of `versions`.

    Gradle refuses to run on a JDK it does not support: current Gradle rejects 26 and drops
    support for 8, so solr, lucene and spring-framework could not be built here at all. Given
    a supported JDK the same builds work, so the runner points Gradle at one explicitly
    instead of inheriting whatever JAVA_HOME happens to be.
    """
    roots = [Path(r"C:/Program Files/Java"), Path(r"C:/Program Files/Eclipse Adoptium"),
             Path.home() / ".jdks", Path.home() / "AppData/Local/Programs/Java",
             Path(r"C:/Program Files/Microsoft"), Path(r"C:/Program Files/Amazon Corretto"),
             Path(r"C:/Program Files/Zulu")]
    for want in versions:
        for root in roots:
            if not root.is_dir():
                continue
            for d in sorted(root.iterdir()):
                if (d.is_dir() and want in d.name
                        and (d / "bin" / "javac.exe").exists()):
                    return d
    return None


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


def _stage_classes(dirs: List[Path], stage: Path) -> Path:
    """Copy every module's classes under ONE root so Arcan builds ONE graph.

    Arcan takes a single `-p` folder and recurses it, so running it once per module can never
    see a smell that crosses modules. Measured on log4j2 (39 modules, 3194 classes): one
    merged run found 599 package cycles and 184 unstable dependencies, against 535 and 131
    for the same 39 modules run separately and summed. 104 of the merged findings span
    modules with disjoint ownership - a cycle between `...log4j.spi` (log4j-api) and
    `...log4j.core.context.internal` (log4j-core), for instance, is unreachable from either
    module alone. Merging is also faster: 95s against 162s, one JVM start instead of 39.

    The repo root is NOT handed to Arcan directly. `_class_dirs` deliberately selects
    `target/classes` only, and the root would also sweep test-classes, generated and shaded
    output, so a before/after pair would stop counting the same set of code.
    """
    # ponytail: plain copy. Class trees are small (log4j2 is 3194 files); switch to
    # os.link if the I/O ever shows up next to Arcan's own runtime.
    shutil.rmtree(stage, ignore_errors=True)
    for i, d in enumerate(dirs):
        # <module>/target/classes -> stage/<i>_<module>. The index keeps two same-named
        # modules in a nested reactor from overwriting each other's classes.
        name = d.parts[-3] if len(d.parts) >= 3 else d.name
        shutil.copytree(d, stage / f"{i}_{name}")
    return stage


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
    # ONE run over every module's classes rather than one run per module - see _stage_classes
    # for why, and for what the per-module version could not detect.
    stage = Path(out_dir) / "_stage" if len(dirs) > 1 else None
    target = _stage_classes(dirs, stage) if stage else dirs[0]
    try:
        r = run_arcan(target, Path(out_dir) / "arcan", log_path=arcan_log)
    finally:
        if stage:
            shutil.rmtree(stage, ignore_errors=True)
    findings: List[Dict[str, Any]] = r.get("findings", [])
    counts = collections.Counter(f["smell_type"] for f in findings)
    measured = r["status"] == "ok"
    return {"ok": measured, "status": r["status"], "measured": measured,
            "smells": len(findings) if measured else None,
            "by_type": dict(counts), "findings": findings,
            "compile": {k: v for k, v in comp.items() if k != "tail"},
            "merged": bool(stage), "modules": [{"classes": str(d)} for d in dirs],
            "tool": "Arcan 1.2.1"}


def _test_counts(line: str):
    """The four numbers in a surefire summary line, or None if it is not one.

    Hand-parsed rather than matched: building this pattern by interpolation is how an escape
    got eaten elsewhere in this codebase and silently produced a pattern that matched
    nothing. There is nothing to escape in a character scan.
    """
    if "Tests run:" not in line:
        return None
    out = []
    for key in ("Tests run:", "Failures:", "Errors:", "Skipped:"):
        i = line.find(key)
        if i == -1:
            return None
        num = ""
        for ch in line[i + len(key):].lstrip():
            if ch.isdigit():
                num += ch
            else:
                break
        if not num:
            return None
        out.append(int(num))
    return out


# Surefire names each failing test on its own line: "[ERROR]   ClassName.method:53 ...".
# Counts alone cannot tell "the same six tests still fail" from "six different ones now fail",
# and log4j2 starts red with 6 failures and 29 errors, so that distinction is the whole
# comparison on that repository.
_FAILING_TEST = re.compile(r"^\[ERROR\]\s{2,}([A-Z][A-Za-z0-9_$]*\.[A-Za-z_][A-Za-z0-9_$]*)[:\s]")


def failing_tests(out: str) -> List[str]:
    """Identities of the tests that failed, as Class.method."""
    found = []
    for line in out.splitlines():
        m = _FAILING_TEST.match(line.rstrip())
        if m and m.group(1) not in found:
            found.append(m.group(1))
    return sorted(found)


def modules_for(repo_path: Path, changed: Iterable[Path]) -> List[str]:
    """The Maven modules that own these files, as reactor-relative paths.

    A refactoring's blast radius is not the whole reactor. Spoon rewrites every reference it
    changes, so the set of files it touched already includes the downstream modules that used
    the moved type: on log4j2, ScriptArbiter touched one module of thirty-seven, and on pdfbox
    COSObjectable touched one of nine. Testing those instead of everything is the difference
    between a four-minute rejection and a thirty-six minute one.
    """
    repo_path = Path(repo_path).resolve()
    mods = set()
    for f in changed:
        p = Path(f)
        p = p if p.is_absolute() else repo_path / p
        for parent in p.resolve().parents:
            if (parent / "pom.xml").exists():
                if parent == repo_path:
                    return ["."]          # the root module owns it; no scoping is possible
                try:
                    mods.add(parent.relative_to(repo_path).as_posix())
                except ValueError:
                    pass
                break
    return sorted(mods)


def run_tests(repo_path: Path, timeout: int = 3600,
              log_path: Optional[Path] = None,
              modules: Optional[List[str]] = None,
              fail_fast: bool = False,
              only: Optional[List[str]] = None) -> Dict[str, Any]:
    """Run the project's OWN test suite against the refactored code.

    `only` narrows Maven to those test classes, for rerunning a suspect; such a run is partial.

    `modules` restricts the reactor to those paths and what they depend on (`-pl ... -am`).
    That is a FILTER, not a verdict: a module that uses the moved type reflectively is not in
    the changed set and will not be tested, which is how tika's ParseContext moves passed
    every structural check and broke thirty-seven tests. Use it to reject candidates cheaply,
    then run unscoped before believing one.

    "It compiles" is a weak guarantee: a refactoring can compile perfectly and still change
    behaviour. The project's tests are the strongest behavioural evidence available without
    writing new ones, and every repository DSARP targets already ships them.

    Returned separately from the smell measurement so a run can report "smells reduced but
    tests failed" honestly, rather than collapsing both into one verdict.
    """
    repo_path = Path(repo_path)
    if not (repo_path / "pom.xml").exists():
        # A Gradle project is not an unverifiable project. Three of the cloned repositories
        # build this way, and returning no_pom here meant their refactorings could compile but
        # never be accepted, because the behavioural gate is the only gate that accepts.
        if gradle_wrapper(repo_path):
            return run_tests_gradle(repo_path, timeout=timeout, log_path=log_path,
                                    fail_fast=fail_fast)
        return {"ok": False, "status": "no_pom"}
    mvn = find_mvn()
    if not mvn:
        return {"ok": False, "status": "maven_not_found"}
    skips = ["-Drat.skip=true", "-Dcheckstyle.skip=true", "-Denforcer.skip=true",
             "-Dspotless.check.skip=true", "-Dspotbugs.skip=true", "-Dpmd.skip=true",
             "-Danimal.sniffer.skip=true", "-Dlicense.skip=true", "-Djacoco.skip=true",
             "-Dmaven.javadoc.skip=true"]
    # -fae (fail at end): without it the reactor stops at the first failing module and every
    # later module is SKIPPED, so the failure count is a lower bound taken mid-run. tika
    # reported "1 failure in 734 tests" having run 4 of its 123 modules, and log4j2 "35
    # broken" having run 7 of 41. A number that can only be wrong in one direction is not
    # evidence. Costs wall time on a repo that is failing; a timeout is reported as
    # test_timeout and is honest, which a silently partial pass is not.
    # -ff stops at the first failing module. That is worthless for accepting a candidate --
    # the counts are a lower bound taken mid-run -- and it is exactly right for rejecting one,
    # because a single genuine failure is enough. tika spends 2186 seconds proving a broken
    # candidate broken with -fae. The result is marked partial so nothing can accept on it.
    #
    # -fae alone is not enough: it still skips every module depending on a failed one. log4j2's
    # log4j-api-test is red before any change, so 27 of 42 modules were skipped, no layout test
    # ran, and a move of a layout class "passed" on 948 tests. failure.ignore keeps the reactor
    # going past a red test module; anything still SKIPPED is reported and makes the run partial.
    keep_going = [] if fail_fast else ["-Dmaven.test.failure.ignore=true"]
    for stale in repo_path.glob("**/target/surefire-reports/TEST-*.xml"):
        stale.unlink(missing_ok=True)
    cmd = [mvn, "-B", "-ntp", "-ff" if fail_fast else "-fae",
           "-f", str(repo_path / "pom.xml"), "test", *skips, *keep_going]
    if only:
        cmd += ["-Dtest=" + ",".join(only), "-Dsurefire.failIfNoSpecifiedTests=false",
                "-DfailIfNoTests=false"]
    scoped = [m for m in (modules or []) if m and m != "."]
    if scoped:
        # -am makes the scoped reactor resolvable without installing anything; -amd is the
        # part that makes it CORRECT. Projects routinely keep a module's tests in a separate
        # module -- log4j-core's tests live in log4j-core-test, tika's detector tests in
        # tika-parsers-standard-integration-tests -- and neither is in the changed set. Scoped
        # to the changed modules alone, log4j2 ran zero tests and reported success.
        cmd += ["-pl", ",".join(scoped), "-am", "-amd"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "test_timeout", "note": f"exceeded {timeout}s"}
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text(out, encoding="utf-8")
    # Every module in a Maven reactor prints its OWN surefire summary; there is no aggregate
    # line to find. Taking the last match reported only the final module, so pdfbox came back
    # as "38 tests" when its io module alone ran 122, and a failure in an early module showed
    # up as status=failed with failures=0 -- the tika inconsistency that went untraced.
    run = fails = errs = skipped = 0
    failing_modules = []
    for ln in out.splitlines():
        # Lines carrying "Time elapsed" are single test CLASSES, already counted by the
        # module summary they sit under; counting both would double every total.
        if "Time elapsed" in ln:
            continue
        counts = _test_counts(ln)
        if counts is None:
            continue
        run += counts[0]
        fails += counts[1]
        errs += counts[2]
        skipped += counts[3]
        if counts[1] or counts[2]:
            failing_modules.append(ln.strip()[:160])
    ok = proc.returncode == 0 and not fails and not errs
    result = {"ok": ok, "status": "passed" if ok else "failed",
              "returncode": proc.returncode, "command": " ".join(cmd),
              "tail": out[-2500:]}
    if run or fails or errs:
        result.update(tests_run=run, failures=fails, errors=errs, skipped=skipped,
                      failing_modules=failing_modules, failing_tests=failing_tests(out)[:200])
    result["outcomes"] = surefire_outcomes(repo_path)
    result["skipped_modules"] = reactor_skipped(out)
    # A fail-fast run, one restricted to part of the reactor, or one that skipped modules has
    # not seen the whole suite. Callers may reject on it; tests_no_worse refuses to accept on it.
    result["partial"] = bool(fail_fast or result["skipped_modules"] or only
                             or [m for m in (modules or []) if m and m != "."])
    return result


def reactor_skipped(out: str) -> List[str]:
    """Modules Maven's reactor summary lists as SKIPPED: tests that never ran."""
    return [m.group(1).strip() for m in
            re.finditer(r"^\[INFO\] (.+?) \.*\s*SKIPPED\s*$", out, re.MULTILINE)]


_XML_ILLEGAL = re.compile("[^\t\n\r\x20-퟿-�\U00010000-\U0010ffff]"
                          r"|&#0*(?:[0-8]|1[124-9]|2\d|3[01]|6553[45]);"
                          r"|&#[xX]0*(?:[0-8bBcCeEfF]|1[0-9a-fA-F]|[fF]{3}[eEfF]);")


def surefire_outcomes(repo_path: Path) -> Dict[str, str]:
    """Outcome per test ID from surefire's XML, which no console format change can break."""
    out: Dict[str, str] = {}
    for path in Path(repo_path).glob("**/target/surefire-reports/TEST-*.xml"):
        try:
            cases = list(ElementTree.parse(path).getroot().iter("testcase"))
        except ElementTree.ParseError:
            # A failure message can quote what XML forbids: commons-text's two failures reported
            # U+FFFE and hid the other 32 tests of their class as "stopped running".
            text = path.read_text(encoding="utf-8", errors="replace")
            try:
                cases = list(ElementTree.fromstring(_XML_ILLEGAL.sub("", text)).iter("testcase"))
            except ElementTree.ParseError:
                continue
        for case in cases:
            state = "passed"
            for tag in ("failure", "error", "skipped"):
                if case.find(tag) is not None:
                    state = tag
            # Parameterised runs share an ID: log4j2 has 10794 runs and 10588 IDs. A later pass
            # must not hide an earlier failure.
            test = "%s#%s" % (case.get("classname"), case.get("name"))
            if out.get(test) not in ("failure", "error"):
                out[test] = state
    return out


def tests_no_worse(baseline: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Is this test run at least as good as the baseline one?

    Not just "are there fewer failures". Moving PDFDebugger left pdfbox reporting zero
    failures and zero errors -- on 1994 tests against a baseline of 2050. Fifty-six tests had
    stopped running, and a comparison of failure counts alone reads that as a pass. Several of
    these repositories are red before anything is changed (log4j2: 6 failures, 29 errors), so
    the comparison has to be against the baseline rather than against zero.
    """
    if baseline.get("partial"):
        return {"ok": False, "partial": True, "why": "the baseline itself was a partial run"}
    before_ids, after_ids = baseline.get("outcomes"), after.get("outcomes")
    if before_ids and after_ids is not None and not after.get("partial"):
        # By identity when surefire's XML exists: a red baseline, and one test dropping out
        # while another appears, cannot hide behind matching totals.
        stopped = sorted(t for t, s in before_ids.items() if s == "passed" and t not in after_ids)
        newly = sorted(t for t, s in before_ids.items() if s == "passed"
                       and after_ids.get(t) in ("failure", "error"))
        return {"ok": not stopped and not newly, "tests_not_run": len(stopped),
                "stopped_running": stopped[:20], "newly_failing": newly[:20],
                "appeared": sorted(set(after_ids) - set(before_ids))[:20],
                "extra_failures": len(newly), "extra_errors": 0,
                "why": ("%d tests that passed before now fail: %s"
                        % (len(newly), ", ".join(newly[:3]))) if newly else None,
                "baseline_was_red": any(s in ("failure", "error") for s in before_ids.values())}
    fewer = max(0, (baseline.get("tests_run") or 0) - (after.get("tests_run") or 0))
    worse_f = (after.get("failures") or 0) - (baseline.get("failures") or 0)
    worse_e = (after.get("errors") or 0) - (baseline.get("errors") or 0)
    if after.get("partial"):
        # A fail-fast or module-scoped run can reject, never accept: its counts are a lower
        # bound. Scoped to the changed modules alone, log4j2 ran zero tests and "passed".
        return {"ok": False, "partial": True,
                "why": "a partial run cannot accept a candidate",
                "extra_failures": max(0, worse_f), "extra_errors": max(0, worse_e)}
    # Counts cannot tell "the same six tests still fail" from "six different ones now fail",
    # and log4j2 starts red with 6 failures and 29 errors. Identities can, when surefire
    # printed them: a test that was not failing before and is failing now is a regression
    # however the totals move.
    before_set = set(baseline.get("failing_tests") or [])
    after_set = set(after.get("failing_tests") or [])
    newly = sorted(after_set - before_set) if (before_set or after_set) else []
    return {"ok": not fewer and worse_f <= 0 and worse_e <= 0 and not newly,
            "tests_not_run": fewer, "extra_failures": max(0, worse_f),
            "extra_errors": max(0, worse_e),
            "newly_failing": newly[:20],
            "why": ("%d tests that passed before now fail: %s"
                    % (len(newly), ", ".join(newly[:3]))) if newly else None,
            "baseline_was_red": bool((baseline.get("failures") or 0)
                                     or (baseline.get("errors") or 0))}


def _junit_xml_totals(repo_path: Path) -> Dict[str, Any]:
    """Test totals and failing-test identities from Gradle's JUnit XML reports.

    Gradle writes <module>/build/test-results/test/TEST-*.xml, which is structured data rather
    than console text. That makes it a better source than the surefire output parsed above:
    the identities come out exactly, so the identity comparison in tests_no_worse works on
    Gradle projects without a second parser for a second console format.
    """
    import xml.etree.ElementTree as ET
    run = fails = errs = skipped = 0
    failing: List[str] = []
    seen_any = False
    for xml in Path(repo_path).rglob("build/test-results/test/TEST-*.xml"):
        try:
            root = ET.parse(xml).getroot()
        except ET.ParseError:
            continue
        seen_any = True
        suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
        for s in suites:
            run += int(s.get("tests") or 0)
            fails += int(s.get("failures") or 0)
            errs += int(s.get("errors") or 0)
            skipped += int(s.get("skipped") or 0)
            for case in s.findall("testcase"):
                if case.find("failure") is not None or case.find("error") is not None:
                    name = "%s.%s" % ((case.get("classname") or "").rsplit(".", 1)[-1],
                                      case.get("name") or "")
                    if name not in failing:
                        failing.append(name)
    return {"found": seen_any, "tests_run": run, "failures": fails, "errors": errs,
            "skipped": skipped, "failing_tests": sorted(failing)[:200]}


def run_tests_gradle(repo_path: Path, timeout: int = 5400,
                     log_path: Optional[Path] = None,
                     fail_fast: bool = False) -> Dict[str, Any]:
    """Run a Gradle project's own test suite, so its refactorings can have a verdict.

    Three of the twenty-two cloned repositories build with Gradle -- lucene, solr and
    spring-framework -- and spring-framework alone holds 215 of the 457 structural refactorings
    mined from history. Until now `run_tests` returned `no_pom` for all three, so a Gradle
    refactoring could be applied and compiled but never accepted: the behavioural gate, which
    is the only gate that can accept, could not run at all.

    `--continue` is Gradle's `-fae`: without it the build stops at the first failing module and
    the totals are a lower bound taken mid-run, which is the same trap the Maven path documents.
    """
    repo_path = Path(repo_path)
    gw = gradle_wrapper(repo_path)
    if not gw:
        return {"ok": False, "status": "gradle_not_found",
                "note": "No gradlew wrapper and no gradle on PATH."}
    cmd = [gw, "test", "--console=plain", "--no-daemon"]
    if not fail_fast:
        cmd.append("--continue")
    env = dict(os.environ)
    jdk = jdk_home_for("21", "17")
    if jdk:
        env["JAVA_HOME"] = str(jdk)
        cmd.append(f"-Dorg.gradle.java.home={jdk}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              cwd=str(repo_path), env=env)
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "test_timeout", "note": f"exceeded {timeout}s",
                "build_tool": "gradle"}
    except OSError as exc:
        return {"ok": False, "status": "gradle_failed", "note": str(exc)[:200]}
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text(out, encoding="utf-8")
    totals = _junit_xml_totals(repo_path)
    if not totals["found"]:
        # No reports at all means the suite never ran. Reporting zero failures here would be
        # the Gradle spelling of "zero failures on fewer tests is not a pass".
        return {"ok": False, "status": "no_test_reports", "build_tool": "gradle",
                "returncode": proc.returncode, "tail": out[-2000:]}
    ok = proc.returncode == 0 and not totals["failures"] and not totals["errors"]
    return {"ok": ok, "status": "passed" if ok else "failed", "build_tool": "gradle",
            "returncode": proc.returncode, "partial": bool(fail_fast),
            "tests_run": totals["tests_run"], "failures": totals["failures"],
            "errors": totals["errors"], "skipped": totals["skipped"],
            "failing_tests": totals["failing_tests"], "tail": out[-2000:]}
