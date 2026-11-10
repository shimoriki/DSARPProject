"""The checks a refactoring must pass, in the order they cost, with the reason each exists.

Every rule here was added because a candidate got the wrong verdict without it, and every one
of them was first written inside a throwaway driver script. That is why this module exists:
the rules kept being re-derived per script, and twice a script shipped without one that the
package already had -- a cycle that shrank was counted as a new cycle, and a test suite that
stopped running 56 tests was counted as a pass.

Order matters. A rejection should cost seconds, not the six minutes a compile takes or the
thirty-six a tika test run takes:

    before_apply   text references, public API        free, before anything is copied
    after_apply    the old name must be gone          seconds, before the compile
    structural     the targeted edge, and its cost    after the build succeeds
    behavioural    the project's own tests            last, and only this can accept

Nothing here applies a refactoring or decides which to try; it only judges one that was.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..refactoring.name_refs import declared_public, name_references, residual
from ..tools.archunit_runner import edge_verdict
from ..tools.arcan_runner import tests_no_worse


def before_apply(repo_path: Path, fqn: str) -> Dict[str, Any]:
    """What a move of `fqn` will break that no compiler and no dependency graph can see.

    Never blocking on its own: pdfbox's debugger-app/pom.xml named the moved class as its
    <mainClass> and the fix was to rewrite the pom, not to abandon the refactoring. It is a
    warning with a file list, and it is free.
    """
    refs = name_references(repo_path, fqn)
    return {"ok": not refs["needs_manual_fixup"],
            "text_references": refs["resources"] + refs["string_literals"],
            "public_api": declared_public(repo_path, fqn),
            # Both are reasons to review, not to refuse.
            "why": ("%d files name this class as text; a move does not rewrite them"
                    % refs["count"]) if refs["needs_manual_fixup"] else None}


def after_apply(work_copy: Path, old_fqn: str) -> Dict[str, Any]:
    """The applier's own post-condition: the old name is gone from the tree.

    OpenRewrite 5.42.1 moved pdfbox's Loader and left two test files importing it; 6.46.1
    moved log4j2's @Required and left RegexFilter.java importing and using it. Both reported
    success, both broke the build, and both took a full compile to expose.
    """
    r = residual(work_copy, old_fqn)
    return {"ok": r["ok"], "files": r["files"],
            "why": None if r["ok"] else
                   "%d files still name %s after the move" % (r["count"], old_fqn)}


REFLECTIVE = ("Class.forName(", "ServiceLoader", "MethodHandles.", ".newInstance(")


def reflection(repo_path: Path, work_copy: Path) -> Dict[str, Any]:
    """A cycle hidden from bytecode is not a cycle removed.

    A dependency turned into a `Class.forName` or `ServiceLoader` lookup leaves jdeps, ArchUnit
    and Arcan nothing to see, as in Ant's XalanExecutor. Counted over the changed files only,
    original against copy, so a moved file that already did a lookup is not counted twice.
    """
    from ..experiments.edge_measure import _changed_java
    repo, root = Path(repo_path).resolve(), Path(work_copy).resolve()
    after_files, before_files = [], []
    for p in map(lambda q: Path(q).resolve(), _changed_java(repo_path, work_copy)):
        if p.is_relative_to(root):
            after_files.append(p)
            # _changed_java names only the copy's side of an edited file; compare it with its
            # own original, or every edited file that already did a lookup reads as adding one.
            # That rejected 9 of 29 Holdout rows on 2026-11-04.
            if (repo / p.relative_to(root)).exists():
                before_files.append(repo / p.relative_to(root))
        else:
            before_files.append(p)

    def count(files: List[Path]) -> Dict[str, int]:
        texts = [f.read_text(encoding="utf-8", errors="replace") for f in files]
        return {s: sum(t.count(s) for t in texts) for s in REFLECTIVE}

    before, after = count(before_files), count(after_files)
    added = [s for s in REFLECTIVE if after[s] > before[s]]
    return {"ok": not added, "added": added,
            "why": "adds reflective lookups: %s" % ", ".join(added) if added else None}


def comparable(before: Dict[str, Any], after: Dict[str, Any],
               tolerance: float = 0.02) -> Dict[str, Any]:
    """Were the two snapshots taken over the same code?

    An edge disappears when the classes carrying it are refactored away, and equally when they
    were never compiled. compile_repo deliberately drops modules whose third-party
    dependencies cannot be obtained, so an after-run that lost a module reports fewer
    packages, fewer edges, and a targeted edge that is "gone". Arcan's importer has already
    been caught making "no classes" and "no cycles" the same answer once; this is the same
    failure with a different cause, so it is checked rather than assumed.

    A small drop is expected and allowed: the moved class itself changes the counts, and a
    refactoring can legitimately empty a package.
    """
    for key in ("classDirs", "classes"):
        b, a = before.get(key), after.get(key)
        if not b or a is None:
            continue
        if a < b * (1 - tolerance):
            return {"ok": False,
                    "why": "the after snapshot covers %s %s against %s before; a module "
                           "probably failed to build" % (a, key, b)}
    return {"ok": True}


def structural(before: Dict[str, Any], after: Dict[str, Any],
               frm: str, to: str) -> Dict[str, Any]:
    """Did the targeted package edge go, and what did it cost? Delegates to the oracle."""
    v = edge_verdict(before, after, frm, to)
    if not v.get("answerable"):
        return {"ok": False, "why": v.get("why"), **v}
    cov = comparable(before, after)
    if not cov["ok"]:
        return {"ok": False, "why": cov["why"], **v}
    return {"ok": bool(v["clean"]),
            "why": None if v["clean"] else
                   ("the edge is still there" if not v["edge_removed"]
                    else "a new cycle appeared"), **v}


def behavioural(baseline_tests: Dict[str, Any],
                after_tests: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The project's own tests, against its own baseline. The only check that can accept."""
    if not after_tests:
        return {"ok": False, "state": "INVALID", "why": "tests were not run"}
    v = tests_no_worse(baseline_tests, after_tests)
    if v["ok"]:
        return {**v, "state": "PASS"}
    # A partial run proves a failure it saw, and proves nothing else. Calling the rest FAIL
    # would blame the refactoring for tests that never ran.
    unproven = v.get("partial") and not (v.get("extra_failures") or v.get("extra_errors"))
    return {**v, "state": "INVALID" if unproven else "FAIL", "why": v.get("why") or
            ("%d tests stopped running" % v["tests_not_run"] if v.get("tests_not_run")
             else "%d new failures, %d new errors"
                  % (v.get("extra_failures", 0), v.get("extra_errors", 0)))}


def settle_flakes(verdict: Dict[str, Any], baseline_runs: List[Dict[str, str]],
                  candidate_runs: List[Dict[str, str]]) -> Dict[str, Any]:
    """Rerun evidence for tests that newly failed. A flake may reject, never accept.

    log4j2's JsonTemplateLayoutNullEventDelimiterTest binds a socket: it failed on an untouched
    baseline in the spike and passed on another. A test is a regression when the candidate
    fails it in more reruns than the baseline does, so no single lucky pass clears one. A test
    the candidate's rerun never ran counts as failed there.
    """
    def bad(run: Dict[str, str], test: str) -> bool:
        return run.get(test) in ("failure", "error")

    real, flaky = [], []
    for test in verdict.get("newly_failing") or []:
        on_candidate = sum(bad(r, test) or test not in r for r in candidate_runs)
        on_baseline = sum(bad(r, test) for r in baseline_runs)
        (real if on_candidate > on_baseline else flaky).append(test)
    if real or verdict.get("tests_not_run"):
        return {**verdict, "newly_failing": real, "flaky": flaky,
                "why": "%d tests fail more on the candidate: %s" % (len(real), ", ".join(real[:3]))
                if real else verdict.get("why")}
    return {**verdict, "ok": True, "state": "PASS", "newly_failing": [], "flaky": flaky,
            "extra_failures": 0, "why": None}


def dispatch(before: Dict[str, List[str]], after: Dict[str, List[str]],
             renames: Dict[str, str]) -> Dict[str, Any]:
    """Service providers, and the order a name sort puts them in, across a move.

    Moving tika's FileCommandDetector compiled, and silently changed detection priority,
    because ServiceLoaderUtils sorts providers by class name. Only one test happened to notice.
    `renames` maps old names to new, so an updated service file is not read as a change.
    """
    for service, names in before.items():
        expected = [renames.get(n, n) for n in names]
        now = after.get(service, [])
        if sorted(expected) != sorted(now):
            return {"ok": False, "why": "providers of %s changed" % service}
        if [renames.get(n, n) for n in sorted(names)] != sorted(now):
            return {"ok": False, "why": "name order of %s providers changed" % service}
    return {"ok": True}


def decide(**checks: Dict[str, Any]) -> Dict[str, Any]:
    """Accept only when every check that ran passed, and say which one refused.

    `before_apply` and `api` are advisory: they report, and a candidate is not refused for
    them. Everything else is a gate. `state` is PASS, FAIL, or INVALID when the only reason
    for refusing is that the evidence was incomplete; INVALID is not a finding about the
    refactoring and must be reported apart from FAIL.
    """
    advisory = {"before_apply", "api"}
    failed = [name for name, r in checks.items()
              if name not in advisory and r is not None and not r.get("ok")]
    warn = [name for name in advisory
            if checks.get(name) is not None and not checks[name].get("ok")]
    invalid = bool(failed) and all(checks[n].get("state") == "INVALID" for n in failed)
    return {"accepted": not failed,
            "state": "PASS" if not failed else "INVALID" if invalid else "FAIL",
            "failed_gate": failed[0] if failed else None,
            "why": checks[failed[0]].get("why") if failed else None,
            "warnings": {n: checks[n].get("why") for n in warn}}
