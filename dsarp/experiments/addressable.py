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

from ..refactoring.java_text import body_range
from .smell_reduction import is_test_code

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

#: Smell types the stock catalogue measurably removed, with the measured yield -- not the number
#: of findings of that type. The catalogue ran over every finding in the repository, so a finding
#: of a type it only partly cleared is one it saw and did not fire on: the remainder is counted as
#: having no working operation, not as reachable. Which individual rows were the lucky ones is not
#: recoverable from the counts, so the budget below is spent in row order; the totals are the
#: measurement, the row-level assignment within a type is arbitrary.
MEASURED = {"Complex Conditional": 6, "Long Statement": 1}

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
    """The suppression marker inside the member declared at `start_line`, or None.

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
    span = body_range(lines, start)
    if span is None:
        return None
    blob = "\n".join(lines[span[0]:span[1] + 1]).lower()
    return next((m for m in SUPPRESSIONS if m in blob), None)


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
        return {"bucket": NEEDS_MEANING,
                "why": "extraction is mechanical; a meaningful name for %s is not"
                       % (value or "the literal")}

    if smell in MEASURED:
        left = MEASURED[smell] if budget is None else budget.get(smell, 0)
        if left > 0:
            if budget is not None:
                budget[smell] = left - 1
            return {"bucket": READY, "why": "stock static analysis removed %d of these, measured"
                                            % MEASURED[smell]}
        return {"bucket": NO_OPERATION,
                "why": "the stock catalogue ran over this one and did not change it; only %d of "
                       "this type were removed" % MEASURED[smell]}
    if smell in IMPROVABLE_NOT_CURABLE:
        return {"bucket": NEEDS_MEANING,
                "why": "moves are validated but no cycle has ever been dissolved here, so this "
                       "improves rather than clears"}
    return {"bucket": NO_OPERATION, "why": "no operation in the toolkit targets this type"}


def analyse(designite_dir: Path) -> Dict[str, Any]:
    """Bucket every production finding in a Designite output directory."""
    designite_dir = Path(designite_dir)
    rows: List[Dict[str, str]] = []
    for name in ("ImplementationSmells", "DesignSmells", "ArchitectureSmells"):
        f = designite_dir / (name + ".csv")
        if f.exists():
            rows += list(csv.DictReader(f.open(encoding="utf-8-sig")))

    cache: Dict[str, str] = {}
    budget = dict(MEASURED)
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
    return {"production_smells": production, "test_code_smells": test_code,
            "buckets": dict(buckets), "by_type": {k: dict(v) for k, v in per_type.items()},
            "reasons": {k: dict(v) for k, v in reasons.items()},
            "adjudicated": buckets[ADJUDICATED],
            "reachable": buckets[READY] + buckets[NEEDS_MEANING],
            "reachable_pct": round(100.0 * (buckets[READY] + buckets[NEEDS_MEANING])
                                   / production, 1) if production else None}


def report(designite_dir: Path) -> str:
    a = analyse(designite_dir)
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
    print(report(Path(sys.argv[1])))
