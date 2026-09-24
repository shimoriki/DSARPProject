"""Run OpenRewrite recipes via Maven to perform the ACTUAL refactoring on real source.

Flow: derive concrete class moves from the cyclic suggestions -> write a `rewrite.yml`
(a ChangeType recipe per class) at the repo root -> `mvn rewrite:run` applies it to the
source. OpenRewrite relocates the class + rewrites every reference and import.

Needs Maven (bundled at tools/apache-maven-*/ or on PATH) + a JDK, and the target repo to
build. `run_recipe` is bounded and returns status + a tail of the Maven log.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# rewrite-maven-plugin version (5.x). Overridable via config.
# 5.42.1 applied ChangeType to the class definition and to most references, and left
# two pdfbox TEST files importing the old name -- so the move compiled everywhere
# except where it did not, and the build failed. 6.46.1 rewrites them. Isolated by
# running the identical recipe, repo, heap and flags under each version.
DEFAULT_PLUGIN = "org.openrewrite.maven:rewrite-maven-plugin:6.46.1"
RECIPE_NAME = "com.dsarp.ArchitecturalRefactoring"

# DSARP's own recipe module (tools/dsarp-recipes). Supplies the transformations stock
# rewrite-java exposes only as visitors, plus field-visibility narrowing which it lacks
# entirely. Build with: mvn -f tools/dsarp-recipes/pom.xml install
CUSTOM_RECIPE_GAV = "com.dsarp:dsarp-recipes:1.0.0"
CUSTOM_RECIPES = ("com.dsarp.recipes.ReduceFieldVisibility",
                  "com.dsarp.recipes.ExtractInterfaceForClass")


def custom_recipes_installed() -> bool:
    """True when the DSARP recipe jar is in the local Maven repository."""
    group, artifact, version = CUSTOM_RECIPE_GAV.split(":")
    jar = (Path.home() / ".m2" / "repository" / Path(group.replace(".", "/"))
           / artifact / version / f"{artifact}-{version}.jar")
    return jar.exists()


def build_custom_recipes(timeout: int = 900) -> Dict[str, Any]:
    """`mvn install` the DSARP recipe module so its recipes become referencable."""
    mvn = find_mvn()
    pom = Path(__file__).resolve().parent.parent.parent / "tools" / "dsarp-recipes" / "pom.xml"
    if not mvn:
        return {"ok": False, "status": "maven_not_found"}
    if not pom.exists():
        return {"ok": False, "status": "recipe_module_missing", "pom": str(pom)}
    try:
        proc = subprocess.run([mvn, "-q", "-B", "-ntp", "-f", str(pom), "install"],
                              capture_output=True, text=True, timeout=timeout,
                              env=_build_env())
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "timeout"}
    ok = proc.returncode == 0 and custom_recipes_installed()
    return {"ok": ok, "status": "installed" if ok else "build_failed",
            "gav": CUSTOM_RECIPE_GAV, "recipes": list(CUSTOM_RECIPES),
            "tail": ((proc.stdout or "") + (proc.stderr or ""))[-1500:]}


# Maven's default heap is far too small for the rewrite plugin on a large repo: it holds the
# whole module's LST in memory at once, so Spark/Lucene-sized projects die with an
# OutOfMemoryError that surfaces here only as a non-zero exit. Overridable by exporting
# MAVEN_OPTS/GRADLE_OPTS -- the right heap depends on the machine.
def free_ram_gb() -> Optional[float]:
    """Physical memory actually available right now, via the OS. No dependency."""
    try:
        if os.name == "nt":
            import ctypes

            class _Stat(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            st = _Stat()
            st.dwLength = ctypes.sizeof(_Stat)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return None
            return st.ullAvailPhys / (1024 ** 3)
        return (os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")) / (1024 ** 3)
    except Exception:
        return None


def _build_env(var: str = "MAVEN_OPTS", heap: Optional[str] = None) -> Dict[str, str]:
    """Maven's default heap is far too small for the rewrite plugin on a large repo, but a
    fixed large one is worse: asking for 6g with 1.7g free does not fail slowly, the JVM
    fails to initialise and Windows reports 0xC0000142 with no output, which reads exactly
    like a compile error and is not one. Size it from what is actually free."""
    env = dict(os.environ)
    if heap is None:
        free = free_ram_gb()
        gb = 6 if free is None else max(1, min(6, int(free * 0.6)))
        heap = f"-Xmx{gb}g"
    env.setdefault(var, heap)
    return env


# Maven could not build the dependency classpath. This matters more than it looks: OpenRewrite
# still parses the sources, but without the classpath the LST carries no type attribution, and
# every type-based recipe (ChangeType, ChangeMethodName, our own) then matches NOTHING and the
# build exits 0. "Ran fine, changed no files" and "could not see any types" are the same
# observation unless we separate them here.
_DEP_FAIL = re.compile(r"Could not resolve dependencies|Non-resolvable|"
                       r"Failed to collect dependencies|Could not transfer artifact|"
                       r"Unable to resolve|dependency resolution failed", re.I)


def _classify(out: str, returncode: int, changed: bool) -> str:
    if changed:
        return "changed"
    if "OutOfMemoryError" in out or "GC overhead limit exceeded" in out:
        return "oom"
    if returncode != 0:
        return "failed"
    return "clean_no_types" if _DEP_FAIL.search(out) else "clean"


def _first_errors(out: str, limit: int = 5) -> List[str]:
    """First few [ERROR] lines. On a multi-module build the cause is near the TOP of the log
    and the 2500-char tail only ever shows the reactor summary."""
    hits = [ln.strip() for ln in out.splitlines() if "[ERROR]" in ln or "OutOfMemoryError" in ln]
    return hits[:limit]


def find_mvn() -> Optional[str]:
    """mvn on PATH, else the bundled tools/apache-maven-*/bin/mvn(.cmd)."""
    if shutil.which("mvn"):
        return "mvn"
    tools = Path(__file__).resolve().parent.parent.parent / "tools"
    for pat in ("apache-maven-*/bin/mvn.cmd", "apache-maven-*/bin/mvn"):
        cands = sorted(tools.glob(pat))
        if cands:
            return str(cands[-1].resolve())
    return None


def write_change_type_recipe(repo_path: Path, moves: List[Tuple[str, str]],
                             recipe_name: str = RECIPE_NAME) -> Path:
    """Write rewrite.yml at the repo root: one ChangeType per (oldFQN -> newFQN) move."""
    lines = ["---", "type: specs.openrewrite.org/v1beta/recipe",
             f"name: {recipe_name}",
             "displayName: DSARP architectural refactoring (relocate classes to break smells)",
             "description: Auto-generated by DSARP to mitigate detected architectural smells.",
             "recipeList:"]
    for old, new in moves:
        lines += ["  - org.openrewrite.java.ChangeType:",
                  f"      oldFullyQualifiedTypeName: {old}",
                  f"      newFullyQualifiedTypeName: {new}",
                  "      ignoreDefinition: false"]
    path = Path(repo_path) / "rewrite.yml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# Where a class name survives as text: a service file, a plugin's <mainClass>, a Spring bean,
# a logging config. Nothing type-aware rewrites these, and each one is a runtime failure.
_TEXT_GLOBS = ("**/pom.xml", "**/*.xml", "**/*.properties", "**/*.yml", "**/*.yaml",
               "**/META-INF/services/*", "**/*.json", "**/*.MF")


def write_move_recipe(repo_path: Path, moves: List[Tuple[str, str]],
                      recipe_name: str = RECIPE_NAME,
                      include_text: bool = True) -> Path:
    """A move as OpenRewrite's own documentation says to write one: the type, the strings
    that name it, the text files that name it, then the imports it left behind.

    ChangeType alone is what we ran, and it is not the whole move. Measured on these repos:
    pdfbox's debugger-app/pom.xml names PDFDebugger as its <mainClass>, tika's TikaCLITest
    asserts "<detector class=\"...POIFSContainerDetector\"/>" as a literal, and a Spoon patch
    leaves stale imports for a reviewer to tidy. Each of those is invisible to a type-aware
    recipe and fatal at run time or at review.

    `include_text` turns off the text pass, which is deliberately blunt: a fully-qualified name
    is specific enough to replace safely, but it will also rewrite the name inside prose in a
    changelog. Off for a migration recipe shipped to someone else's repository.
    """
    lines = ["---", "type: specs.openrewrite.org/v1beta/recipe",
             f"name: {recipe_name}",
             "displayName: DSARP architectural refactoring (relocate classes to break smells)",
             "description: Auto-generated by DSARP to mitigate detected architectural smells.",
             "recipeList:"]
    for old, new in moves:
        lines += ["  - org.openrewrite.java.ChangeType:",
                  f"      oldFullyQualifiedTypeName: {old}",
                  f"      newFullyQualifiedTypeName: {new}",
                  "      ignoreDefinition: false",
                  # Class.forName, service lookups, and tests that assert the name.
                  "  - org.openrewrite.java.ChangeTypeInStringLiteral:",
                  f"      oldFullyQualifiedTypeName: {old}",
                  f"      newFullyQualifiedTypeName: {new}"]
        if include_text:
            for glob in _TEXT_GLOBS:
                lines += ["  - org.openrewrite.text.FindAndReplace:",
                          f"      find: {old}",
                          f"      replace: {new}",
                          "      caseSensitive: true",
                          f"      filePattern: '{glob}'"]
    lines += ["  - org.openrewrite.java.RemoveUnusedImports"]
    path = Path(repo_path) / "rewrite.yml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_migration_recipe(out_path: Path, moves: List[Tuple[str, str]],
                           recipe_name: str = RECIPE_NAME + ".Migration") -> Path:
    """The recipe a DOWNSTREAM project runs after we move a public type.

    Moving a public type renames it for everyone who depends on the library, which is the one
    cost the dependency graph cannot see and the reason pdfbox's Loader and COSObjectable are
    major-version changes. OpenRewrite's answer to a breaking change is to ship the recipe that
    fixes it, and we already know every old-to-new pair. No text pass: this runs in a
    repository whose files are not ours.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = write_move_recipe(out_path.parent, moves, recipe_name, include_text=False)
    if tmp.resolve() != out_path.resolve():
        out_path.write_text(tmp.read_text(encoding="utf-8"), encoding="utf-8")
        tmp.unlink()
    return out_path


def write_change_package_recipe(repo_path: Path, merges: List[Tuple[str, str]],
                                recipe_name: str = RECIPE_NAME) -> Path:
    """Write rewrite.yml using ChangePackage: relocate ENTIRE packages (oldPkg -> newPkg).

    Preferred over per-class ChangeType for breaking package cycles. Moving only *some*
    classes out of a package breaks their implicit same-package references (the moved file
    loses access to the siblings it never had to import), so the result does not compile.
    Moving the whole package keeps every intra-package reference intact AND removes the
    package that closed the cycle.
    """
    lines = ["---", "type: specs.openrewrite.org/v1beta/recipe",
             f"name: {recipe_name}",
             "displayName: DSARP architectural refactoring (merge packages to break cycles)",
             "description: Auto-generated by DSARP to mitigate detected architectural smells.",
             "recipeList:"]
    for old, new in merges:
        lines += ["  - org.openrewrite.java.ChangePackage:",
                  f"      oldPackageName: {old}",
                  f"      newPackageName: {new}",
                  "      recursive: false"]
    path = Path(repo_path) / "rewrite.yml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_composite_recipe(repo_path: Path, entries: List[Any],
                           recipe_name: str = RECIPE_NAME) -> Path:
    """Write rewrite.yml from a list of RecipeEntry objects covering ALL smell types.

    Entries come from dsarp.refactoring.strategies, so one run can relocate packages for a
    cyclic smell, split a God Component, consolidate scattered functionality and delete dead
    abstractions in a single OpenRewrite pass.
    """
    lines = ["---", "type: specs.openrewrite.org/v1beta/recipe",
             f"name: {recipe_name}",
             "displayName: DSARP architectural refactoring (all smell types)",
             "description: Auto-generated by DSARP from tool-detected architectural smells.",
             "recipeList:"]
    for e in entries:
        lines.extend(e.to_yaml_lines())
    path = Path(repo_path) / "rewrite.yml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


GRADLE_PLUGIN_VERSION = "6.29.0"       # rewrite-gradle-plugin

# Applied with `--init-script`, so the target repository's own build files are never touched.
# `allprojects` reaches every subproject, which matters for the multi-module Gradle builds
# (Solr, Cassandra, Lucene, Spring) that DSARP could previously only analyse, not refactor.
_GRADLE_INIT = """\
initscript {{
    repositories {{ gradlePluginPortal() }}
    dependencies {{
        classpath 'org.openrewrite:plugin:{version}'
    }}
}}
allprojects {{
    apply plugin: org.openrewrite.gradle.RewritePlugin
    repositories {{ mavenCentral(); mavenLocal() }}
    rewrite {{
        activeRecipe('{recipe}')
        configFile = file('{config}')
        exportDatatables = false
    }}
    dependencies {{
        rewrite '{gav}'
    }}
}}
"""


def write_gradle_init_script(repo_path: Path, recipe_name: str = RECIPE_NAME) -> Path:
    """Init script that applies rewrite-gradle-plugin without editing the repo."""
    repo_path = Path(repo_path)
    config = str((repo_path / "rewrite.yml").resolve()).replace("\\", "/")
    script = repo_path / "dsarp-rewrite-init.gradle"
    script.write_text(_GRADLE_INIT.format(version=GRADLE_PLUGIN_VERSION,
                                          recipe=recipe_name, config=config,
                                          gav=CUSTOM_RECIPE_GAV), encoding="utf-8")
    return script


def recipe_moves(repo_path) -> List[Tuple[str, str]]:
    """(old_fqn, new_fqn) pairs from the ChangeType entries of the generated rewrite.yml.

    Read back from the file rather than threaded through every caller: the moved file needs
    imports for the types it left behind, and run_recipe is the one place that knows a real
    run just happened.
    """
    f = Path(repo_path) / "rewrite.yml"
    if not f.exists():
        return []
    try:
        import yaml
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    out = []
    for item in (doc.get("recipeList") or []):
        if not isinstance(item, dict):
            continue
        for key, val in item.items():
            if str(key).endswith("ChangeType") and isinstance(val, dict):
                o, n = (val.get("oldFullyQualifiedTypeName"),
                        val.get("newFullyQualifiedTypeName"))
                if o and n:
                    out.append((o, n))
    return out


def run_recipe_gradle(repo_path: Path, recipe_name: str = RECIPE_NAME, dry_run: bool = False,
                      timeout: int = 2400, log_path: Optional[Path] = None) -> Dict[str, Any]:
    """Run the generated recipe on a GRADLE project via rewrite-gradle-plugin."""
    from ..tools.arcan_runner import gradle_wrapper
    gw = gradle_wrapper(repo_path)
    if not gw:
        return {"ok": False, "status": "gradle_not_found",
                "note": "No gradlew wrapper and no gradle on PATH."}
    init = write_gradle_init_script(Path(repo_path), recipe_name)
    task = "rewriteDryRun" if dry_run else "rewriteRun"
    cmd = [gw, task, "--init-script", str(init), "--no-daemon", "--console=plain",
           "-x", "test"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              cwd=str(repo_path), env=_build_env("GRADLE_OPTS"))
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"ok": False, "status": "timeout", "note": str(e)[:200]}
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text(out, encoding="utf-8")
    ok = proc.returncode == 0
    changed = ("Changes have been made" in out) or ("Please review and commit" in out)
    files = sorted(set(re.findall(r"Changes have been made to\s+(.+?)\s+by:", out)))
    # ChangeType rewrites the type but leaves behind the debris that fails a quality
    # gate. The identical move compiled under Spoon and came back quality_gate_failed
    # here purely on a now-same-package import, so the cleanup runs for both backends.
    tidy = None
    if changed and not dry_run:
        from ..refactoring.java_text import tidy_tree
        tidy = tidy_tree(repo_path, only=files or None,
                         moves=recipe_moves(repo_path))
    return {"ok": ok, "tidy": tidy, "status": _classify(out, proc.returncode, changed),
            "returncode": proc.returncode, "changed_files": files[:50],
            "recipe": recipe_name, "goal": task, "build_tool": "gradle",
            "errors": _first_errors(out), "tail": out[-2500:], "gradle": gw}


def run_recipe(repo_path: Path, recipe_name: str = RECIPE_NAME, dry_run: bool = False,
               plugin: str = DEFAULT_PLUGIN, timeout: int = 2400,
               log_path: Optional[Path] = None) -> Dict[str, Any]:
    """Run the OpenRewrite recipe already written to <repo>/rewrite.yml."""
    mvn = find_mvn()
    if not mvn:
        return {"ok": False, "status": "maven_not_found",
                "note": "Maven not found (PATH or tools/apache-maven-*)."}
    pom = Path(repo_path) / "pom.xml"
    if not pom.exists():
        # Gradle projects go through rewrite-gradle-plugin instead.
        from ..verification.openrewrite_loop import detect_build_system
        if detect_build_system(repo_path) == "gradle":
            return run_recipe_gradle(repo_path, recipe_name, dry_run,
                                     timeout=timeout, log_path=log_path)
        return {"ok": False, "status": "no_pom",
                "note": "OpenRewrite run needs a Maven pom.xml or a Gradle build."}
    goal = "dryRun" if dry_run else "run"
    # Skip build-audit/quality plugins that would otherwise fail the build before OpenRewrite
    # runs (e.g. apache-rat rejecting our generated rewrite.yml for a missing license header).
    skips = ["-Drat.skip=true", "-Dcheckstyle.skip=true", "-Denforcer.skip=true",
             "-Dmaven.test.skip=true", "-Dspotless.check.skip=true", "-Dspotbugs.skip=true",
             "-Dpmd.skip=true", "-Danimal.sniffer.skip=true", "-Dlicense.skip=true",
             "-Djacoco.skip=true", "-Dmaven.javadoc.skip=true"]
    config = (Path(repo_path) / "rewrite.yml").resolve()
    cmd = [mvn, "-B", "-ntp", "-f", str(pom), f"{plugin}:{goal}",
           f"-Drewrite.activeRecipes={recipe_name}",
           f"-Drewrite.configLocation={config}",
           "-Drewrite.exportDatatables=false", *skips]
    # Put DSARP's custom recipes (field visibility, extract interface) on the plugin's
    # classpath so rewrite.yml can name them alongside the stock ones.
    if custom_recipes_installed():
        cmd.append(f"-Drewrite.recipeArtifactCoordinates={CUSTOM_RECIPE_GAV}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              env=_build_env())
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "timeout", "note": f"exceeded {timeout}s"}
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text(out, encoding="utf-8")
    ok = proc.returncode == 0
    changed = ("Changes have been made" in out) or ("Please review and commit" in out)
    files = sorted(set(re.findall(r"Changes have been made to\s+(.+?)\s+by:", out)))
    # ChangeType rewrites the type but leaves behind the debris that fails a quality
    # gate. The identical move compiled under Spoon and came back quality_gate_failed
    # here purely on a now-same-package import, so the cleanup runs for both backends.
    tidy = None
    if changed and not dry_run:
        from ..refactoring.java_text import tidy_tree
        tidy = tidy_tree(repo_path, only=files or None,
                         moves=recipe_moves(repo_path))
    return {"ok": ok, "tidy": tidy, "status": _classify(out, proc.returncode, changed),
            "returncode": proc.returncode, "changed_files": files[:50],
            "recipe": recipe_name, "goal": goal, "errors": _first_errors(out),
            "tail": out[-2500:], "mvn": mvn}
