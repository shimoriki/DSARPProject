"""How many of a repository's Designite smells can actually be refactored, and why not the rest.

The goal "refactor the majority of smells Designite reports" needs a denominator that is honest
about what is reachable. Three things cap it, and all three are computable from the source rather
than guessed:

  * **published API.** Designite counts a library's own interface as a smell. In
    commons-validator 64 of the 86 exposed fields it flags are `public static final` constants --
    the published API -- and narrowing them does not compile for any consumer. Of 23 classes
    flagged Deficient Encapsulation, exactly one exposes nothing but mutable state.
  * **test code.** Findings in the other categories that sit in a test source root. Unutilized
    Abstraction is 14 test classes to 3 production ones, and Designite's own description hedges
    with "please ignore".
  * **meaning.** Replacing `13` with a constant is a two-line edit; knowing it should be called
    `MAX_LENGTH` and not `CONST_13` is not mechanical. A tool that emits `CONST_13` satisfies the
    detector and leaves the code worse, which is the one outcome this project should not ship.

So a finding is sorted into one of four buckets, and each verdict cites either a measured result
from this repository or a property computed from the source here -- never an opinion about the
smell type alone.

Measured inputs this module relies on, all from apache-commons-validator:
  * the whole stock static-analysis catalogue (`CommonStaticAnalysis`, 216 recipe classes)
    removes 7 of 201 production findings: Complex Conditional -6, Long Statement -1, nothing
    introduced, 1147 tests green. Three hand-picked recipes got 6 of those 7, so the catalogue is
    very nearly exhausted at 3%.
  * no cycle has ever been dissolved here, nor in either hand-refactored expert tree, so the
    cycle-shaped smells are marked as improvable but not curable.
"""
from __future__ import annotations

import collections
import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..refactoring.java_text import body_range, code_only
from .smell_reduction import is_test_code, trial_limit_hit

# Buckets, worst-to-best, so a sort puts what is actually actionable first.
READY = "operation_validated"          # an operation here has removed this type, measured
NEEDS_MEANING = "needs_meaning"        # mechanical edit, but a human or model must name/decide
BLOCKED_API = "blocked_published_api"  # the fix would break the repository's published surface
ADJUDICATED = "already_adjudicated"    # the maintainers suppressed this warning on purpose
NO_OPERATION = "no_operation"          # nothing in the toolkit touches it

#: Markers by which a maintainer records that a warning here was considered and rejected. Finding
#: one is the strongest evidence available that a finding is not a defect: it is the authors of the
#: code saying so in the code. 47 of commons-validator's 68 magic numbers carry one.
SUPPRESSIONS = ("checkstyle ignore", "checkstyle:off", "nopmd", "nosonar", "suppresswarnings",
                "squid:", "@formatter:off")

#: What the stock catalogue measurably removed, PER REPOSITORY. These are measurements, not rates:
#: the yield for one repository says nothing about another, and an earlier version of this module
#: applied commons-validator's numbers to every repository in the corpus, which made `ready` read
#: as exactly 7 everywhere -- a constant that should have been the giveaway.
#:
#: The value is the measured yield, not the number of findings of that type. The catalogue ran over
#: every finding in the repository, so one of a type it only partly cleared is one it saw and did
#: not fire on: the remainder counts as having no working operation, not as reachable. Which
#: individual rows were the lucky ones is not recoverable from the counts, so the budget is spent
#: in row order; the totals are the measurement, the assignment within a type is arbitrary.
MEASURED_BY_REPO: Dict[str, Dict[str, int]] = {
    # CommonStaticAnalysis, 6 files changed, compiles, 1147 tests green, nothing introduced.
    "apache-commons-validator": {"Complex Conditional": 6, "Long Statement": 1},
}

#: Cycle-shaped smells. Moves are validated -- 18 of 18 planned moves applied, built and removed
#: their target edge -- but no cycle has ever been dissolved, so the smell improves, not clears.
IMPROVABLE_NOT_CURABLE = {"Cyclic Dependency", "God Component", "Unstable Dependency",
                          "Scattered Functionality", "Cyclically-dependent Modularization"}

#: Literals not worth naming. `2` in a Luhn checksum is clearer as `2` than as `TWO`, and a
#: constant called `TWO` is detector-satisfying noise.
TRIVIAL_LITERALS = {"0", "1", "2", "-1", "0.0", "1.0", "0L", "1L"}

_FIELD = re.compile(r"^[ \t]{1,8}(public|protected)[ \t]+"
                    r"((?:static[ \t]+|final[ \t]+|transient[ \t]+|volatile[ \t]+)*)"
                    r"[\w.<>\[\],?][\w.<>\[\],?\s]*?[ \t]+(\w+)[ \t]*[=;]", re.M)
_MAGIC = re.compile(r"magic number:\s*(\S+)")


def _source(path: Optional[str]) -> str:
    p = Path(path) if path else None
    if not p or not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="ignore")


def exposed_fields(src: str) -> List[Dict[str, Any]]:
    """Public and protected fields a class declares, and whether each is a published constant.

    `static final` is the distinction that decides whether narrowing is even possible: a mutable
    protected field is internal state that leaked, while a `public static final` is the API.
    """
    out = []
    for m in _FIELD.finditer(src):
        mods = m.group(2) or ""
        out.append({"visibility": m.group(1), "name": m.group(3),
                    "published_constant": "static" in mods and "final" in mods})
    return out


def suppression_in_member(src: str, start_line: Optional[str]) -> Optional[str]:
    """The suppression covering the member declared at `start_line`, or None.

    Two scopes, and missing the second one produced a wrong answer here. A per-line marker inside
    the member is the obvious case. The other is a FILE-LEVEL switch: `// CHECKSTYLE:OFF` with no
    matching `:ON` turns the check off for the rest of the file. commons-validator has exactly two
    such files, `CreditCardValidator.java` and `ISSNValidator.java` -- and between them they hold
    every one of the seven magic numbers that a member-scoped check called "genuinely open". With
    the file scope included, none of that repository's 68 magic numbers is open: 49 are suppressed
    line by line and the rest sit under a blanket switch.

    Searched in the raw text, because a suppression IS a comment. The member's extent comes from
    `body_range`, which strips comments before balancing braces -- Designite points at the javadoc
    line, whose `{@code}` braces otherwise close the member before its body is reached.
    """
    try:
        start = int(start_line)
    except (TypeError, ValueError):
        return None
    lines = src.splitlines()
    if not lines or start < 1 or start > len(lines):
        return None
    switch = _blanket_switch(lines, start)
    if switch:
        return switch
    span = body_range(lines, start)
    if span is None:
        return None
    blob = "\n".join(lines[span[0]:span[1] + 1]).lower()
    return next((m for m in SUPPRESSIONS if m in blob), None)


def _blanket_switch(lines: List[str], start: int) -> Optional[str]:
    """An unclosed `OFF` switch above `start`, which suppresses everything after it.

    Pairs each OFF with a later ON; what is left open at the member's line covers it. A
    `@SuppressWarnings` on the enclosing type counts too, since it applies to every member.
    """
    open_marker = None
    for line in lines[:max(start - 1, 0)]:
        low = line.lower()
        if "checkstyle:off" in low or "@formatter:off" in low:
            open_marker = line.strip()[:60]
        elif "checkstyle:on" in low or "@formatter:on" in low:
            open_marker = None
        elif "@suppresswarnings" in low and "class " not in low:
            # on its own line directly above a type or member declaration
            open_marker = open_marker or line.strip()[:60]
    return open_marker


def bit_level_use(src: str, start_line: Optional[str], value: Optional[str]) -> Optional[str]:
    """Why this literal is a shift amount or a bit mask, if it is, else None.

    commons-codec reports 1049 magic numbers and they are not thresholds: 133 are in
    `Sha2Crypt.sha2Crypt`, 67 in `PureJavaCrc32.update`, 67 in `UnixCrypt.desSetKey`, 59 in
    `MurmurHash3.hash128x64Internal`, 42 in `Blake3.round`. The commonest values are 0xff (99
    times), then 8, 16 and 24. Those are byte masks and shift amounts transcribed from SHA-2,
    CRC-32, DES, MurmurHash and BLAKE3. `x & 0xff` is the universal Java idiom for taking a byte,
    and `(x >>> 24) & 0xff` says which byte; naming either hides the correspondence to the
    published algorithm, which is the only documentation such code has.

    Two signals, both local to the use rather than guessed from the class name:
      * the literal is written in hexadecimal -- an author choosing hex is writing a bit pattern;
      * the literal appears immediately after a shift operator, so it is a shift distance.
    """
    if not value:
        return None
    if value.lower().startswith(("0x", "-0x")):
        return "written in hexadecimal: a bit pattern, not a quantity to name"
    try:
        start = int(start_line)
    except (TypeError, ValueError):
        return None
    lines = src.splitlines()
    if not lines or start < 1 or start > len(lines):
        return None
    span = body_range(lines, start)
    if span is None:
        return None
    body = "\n".join(code_only(lines[span[0]:span[1] + 1]))
    if re.search(r"(?:<<|>>>|>>)\s*" + re.escape(value) + r"(?![\w.])", body):
        return "used as a shift distance; a name would not say which byte it selects"
    return None


def declares_public_type(src: str, simple_name: str) -> bool:
    return re.search(r"public\s+(?:final\s+|abstract\s+|static\s+)*(?:class|interface|enum|record)"
                     r"\s+" + re.escape(simple_name) + r"\b", src) is not None


def classify(row: Dict[str, str], src: str,
             budget: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """One finding's bucket, with the reason that put it there.

    `budget` carries the remaining measured yield per smell type and is decremented, so a type the
    stock catalogue only partly cleared does not report its whole population as reachable.
    """
    smell, cls = row.get("Smell") or "", row.get("Class") or ""
    simple = cls.split(".")[-1]

    if smell == "Deficient Encapsulation":
        fields = exposed_fields(src)
        published = [f for f in fields if f["published_constant"]]
        mutable = [f for f in fields if not f["published_constant"]]
        if published:
            return {"bucket": BLOCKED_API,
                    "why": "exposes %d published static-final constant(s); narrowing them breaks "
                           "every consumer" % len(published)}
        if mutable:
            return {"bucket": READY,
                    "why": "exposes only %d mutable field(s); ReduceFieldVisibility applies"
                           % len(mutable)}
        return {"bucket": NO_OPERATION, "why": "no public or protected field found in the source"}

    if smell in ("Unutilized Abstraction", "Unnecessary Abstraction"):
        if declares_public_type(src, simple):
            return {"bucket": BLOCKED_API,
                    "why": "public type: 'unused' here means used by consumers, not unused"}
        verb = "delete" if smell == "Unutilized Abstraction" else "inline"
        return {"bucket": NEEDS_MEANING,
                "why": "non-public, so %s is possible, but whether it should be is a design call"
                       % verb}

    if smell == "Magic Number":
        lit = _MAGIC.search(row.get("Description") or "")
        value = lit.group(1) if lit else None
        marker = suppression_in_member(src, row.get("Method start line no"))
        if marker:
            return {"bucket": ADJUDICATED,
                    "why": "the method carries '%s'; the maintainers kept this literal on purpose"
                           % marker}
        if value in TRIVIAL_LITERALS:
            return {"bucket": NO_OPERATION,
                    "why": "literal %s is clearer than any name for it" % value}
        bitwise = bit_level_use(src, row.get("Method start line no"), value)
        if bitwise:
            return {"bucket": NO_OPERATION, "why": bitwise}
        return {"bucket": NEEDS_MEANING,
                "why": "extraction is mechanical; a meaningful name for %s is not"
                       % (value or "the literal")}

    if budget and smell in budget:
        left = budget[smell]
        if left > 0:
            budget[smell] = left - 1
            return {"bucket": READY,
                    "why": "stock static analysis removed this type here, measured"}
        return {"bucket": NO_OPERATION,
                "why": "the stock catalogue ran over this one and did not change it"}
    if smell in IMPROVABLE_NOT_CURABLE:
        return {"bucket": NEEDS_MEANING,
                "why": "moves are validated but no cycle has ever been dissolved here, so this "
                       "improves rather than clears"}
    return {"bucket": NO_OPERATION, "why": "no operation in the toolkit targets this type"}


def analyse(designite_dir: Path, repo: Optional[str] = None) -> Dict[str, Any]:
    """Bucket every production finding in a Designite output directory.

    `repo` names the repository so its own measured recipe yield is used. Without it no finding is
    called `operation_validated`, because nothing has been measured here: a yield from another
    repository is not evidence about this one.

    Refuses a directory the trial edition of Designite declined to report on. Those CSVs hold
    their header row and nothing else, so every count reads as a clean zero.
    """
    designite_dir = Path(designite_dir)
    capped = trial_limit_hit(designite_dir)
    if capped:
        return {"ok": False, "trial_limited": True, "production_smells": 0,
                "why": "DesigniteJava trial limit: %s" % capped,
                "buckets": {}, "by_type": {}, "reasons": {},
                "reachable": 0, "reachable_pct": None, "test_code_smells": 0}
    rows: List[Dict[str, str]] = []
    for name in ("ImplementationSmells", "DesignSmells", "ArchitectureSmells"):
        f = designite_dir / (name + ".csv")
        if f.exists():
            rows += list(csv.DictReader(f.open(encoding="utf-8-sig")))

    cache: Dict[str, str] = {}
    budget = dict(MEASURED_BY_REPO.get(repo or "", {}))
    buckets: Dict[str, int] = collections.Counter()
    per_type: Dict[str, Dict[str, int]] = collections.defaultdict(collections.Counter)
    reasons: Dict[str, Dict[str, int]] = collections.defaultdict(collections.Counter)
    test_code = 0
    for r in rows:
        if not r.get("Smell"):
            continue
        if is_test_code(r.get("File")):
            test_code += 1
            continue
        path = r.get("File") or ""
        if path not in cache:
            cache[path] = _source(path)
        verdict = classify(r, cache[path], budget)
        buckets[verdict["bucket"]] += 1
        per_type[r["Smell"]][verdict["bucket"]] += 1
        reasons[r["Smell"]][verdict["why"]] += 1
    production = sum(buckets.values())
    return {"ok": True, "production_smells": production, "test_code_smells": test_code,
            "buckets": dict(buckets), "by_type": {k: dict(v) for k, v in per_type.items()},
            "reasons": {k: dict(v) for k, v in reasons.items()},
            "adjudicated": buckets[ADJUDICATED],
            "reachable": buckets[READY] + buckets[NEEDS_MEANING],
            "reachable_pct": round(100.0 * (buckets[READY] + buckets[NEEDS_MEANING])
                                   / production, 1) if production else None}


def report(designite_dir: Path, repo: Optional[str] = None) -> str:
    a = analyse(designite_dir, repo)
    if not a.get("ok"):
        return "no measurement: %s" % a.get("why")
    lines = ["%d production findings (%d more sit in test source and are excluded)"
             % (a["production_smells"], a["test_code_smells"]), "",
             "%-36s %5s %5s %5s %5s %5s"
             % ("smell", "ready", "mean", "API", "kept", "none")]
    order = sorted(a["by_type"].items(), key=lambda kv: -sum(kv[1].values()))
    for smell, b in order:
        lines.append("%-36s %5d %5d %5d %5d %5d"
                     % (smell[:36], b.get(READY, 0), b.get(NEEDS_MEANING, 0),
                        b.get(BLOCKED_API, 0), b.get(ADJUDICATED, 0), b.get(NO_OPERATION, 0)))
    t = a["buckets"]
    lines += ["", "%-36s %5d %5d %5d %5d %5d"
                  % ("TOTAL", t.get(READY, 0), t.get(NEEDS_MEANING, 0),
                     t.get(BLOCKED_API, 0), t.get(ADJUDICATED, 0), t.get(NO_OPERATION, 0)),
              "",
              "ready   an operation here has removed this type, measured",
              "mean    mechanical, but a name or design decision has to come from somewhere",
              "API     the fix would change this repository's published surface",
              "kept    the maintainers suppressed the warning on purpose",
              "none    nothing in the toolkit targets it",
              "", "reachable (ready + mean): %d of %d = %s%%"
                  % (a["reachable"], a["production_smells"], a["reachable_pct"])]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    print(report(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else None))
