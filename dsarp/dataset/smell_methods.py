"""Build a smell → removal-method dataset from REAL refactorings in real repositories.

Every example is extracted from a commit that actually happened: RefactoringMiner supplies
the commit sha, the refactoring type, and the exact file/line range on both sides, and the
code is read back out of the repository with `git show`. Nothing here is written by a model
or reconstructed from a description.

Two constraints from the brief shape what an example contains:

  * the model must not receive whole source files — it gets a STRUCTURAL descriptor plus
    signatures, never a file dump, so it cannot memorise a repository;
  * the model must not receive Arcan or Designite output — the smell is described by facts
    computed from the source itself (sizes, fan-in/out, cycle participation), so the model
    learns the repair rather than the detector's phrasing.

The label is the refactoring method that was actually applied. Whether that method removed
the smell is a separate, measured field (`outcome`), filled in by the validation pipeline —
it is deliberately not assumed here, because the whole point of the exercise is that
type-correct recommendations often fail to remove anything.
"""
from __future__ import annotations

import collections
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# Refactoring types that operate at the architectural level — the ones a smell-removal
# recommender can actually act on. Method/variable-level renames are excluded: they are the
# bulk of RefactoringMiner's output and none of them move an architectural smell.
ARCHITECTURAL_METHODS = {
    "Move Class", "Move And Rename Class", "Extract Class", "Extract Subclass",
    "Extract Superclass", "Extract Interface", "Move Method", "Move And Rename Method",
    "Move Attribute", "Pull Up Method", "Pull Up Attribute", "Push Down Method",
    "Push Down Attribute", "Extract And Move Method", "Move Source Folder",
    "Change Class Access Modifier", "Encapsulate Attribute", "Merge Class", "Split Class",
    "Split Package", "Merge Package", "Rename Package", "Inline Class",
}

# Which smells each method is documented to address. Sourced from the Designite/Suryanarayana
# catalogue and the Arcan smell definitions — NOT inferred from our own data, and used only
# as a candidate filter, never as a label.
METHOD_TARGETS: Dict[str, List[str]] = {
    "Move Class": ["Cyclic Dependency", "God Component", "Feature Concentration",
                   "Scattered Functionality", "Unstable Dependency", "Hub-Like Dependency"],
    "Move And Rename Class": ["Cyclic Dependency", "Scattered Functionality"],
    "Extract Class": ["Insufficient Modularization", "God Component", "Multifaceted Abstraction"],
    "Extract Interface": ["Cyclic Dependency", "Unstable Dependency", "Broken Modularization"],
    "Extract Superclass": ["Duplicate Abstraction", "Broken Hierarchy"],
    "Extract Subclass": ["Multifaceted Abstraction", "Broken Hierarchy"],
    "Move Method": ["Feature Envy", "Scattered Functionality", "Cyclic Dependency"],
    "Move And Rename Method": ["Feature Envy", "Scattered Functionality"],
    "Move Attribute": ["Feature Envy", "Broken Modularization"],
    "Pull Up Method": ["Duplicate Abstraction", "Broken Hierarchy"],
    "Pull Up Attribute": ["Duplicate Abstraction", "Broken Hierarchy"],
    "Push Down Method": ["Unnecessary Abstraction", "Broken Hierarchy"],
    "Push Down Attribute": ["Unnecessary Abstraction", "Broken Hierarchy"],
    "Extract And Move Method": ["Feature Envy", "Insufficient Modularization"],
    "Move Source Folder": ["Scattered Functionality", "God Component"],
    "Change Class Access Modifier": ["Deficient Encapsulation", "Unutilized Abstraction"],
    "Encapsulate Attribute": ["Deficient Encapsulation"],
    "Inline Class": ["Unnecessary Abstraction", "Unutilized Abstraction"],
    "Merge Class": ["Unnecessary Abstraction"],
    "Split Class": ["Insufficient Modularization", "Multifaceted Abstraction"],
    "Split Package": ["God Component", "Feature Concentration"],
    "Merge Package": ["Unnecessary Abstraction"],
    "Rename Package": ["Scattered Functionality"],
}


@dataclass
class Example:
    """One real refactoring, with everything needed to learn from it and nothing more."""

    repo: str
    sha: str
    method: str                          # the label: what was actually done
    candidate_smells: List[str]           # what this method is documented to address
    before: Dict[str, Any] = field(default_factory=dict)
    after: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    outcome: Optional[Dict[str, Any]] = None   # filled by the validator, never assumed

    def as_dict(self) -> Dict[str, Any]:
        return {"repo": self.repo, "sha": self.sha, "method": self.method,
                "candidate_smells": self.candidate_smells, "before": self.before,
                "after": self.after, "context": self.context, "outcome": self.outcome}


def git_show(repo: Path, sha: str, path: str, timeout: int = 30) -> Optional[str]:
    """A file exactly as it stood at a commit. Read-only; the checkout is never touched."""
    try:
        proc = subprocess.run(["git", "-C", str(repo), "show", f"{sha}:{path}"],
                              capture_output=True, text=True, timeout=timeout,
                              errors="ignore")
    except (subprocess.TimeoutExpired, OSError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _slice(text: str, start: int, end: int, max_lines: int = 60) -> str:
    """The declaration at these lines, capped.

    Capped deliberately: a 333-line class body is the whole file by another name, and the
    brief rules that out. The head of a declaration carries its signature, modifiers and
    fields, which is the part a placement decision turns on.
    """
    lines = text.splitlines()
    lo, hi = max(0, start - 1), min(len(lines), end)
    return "\n".join(lines[lo:min(hi, lo + max_lines)])


def _signature_only(snippet: str, max_lines: int = 25) -> List[str]:
    """Declaration lines only — no statement bodies.

    Keeps package/import/type/field/method signatures and drops everything else, so an
    example describes SHAPE (what this type is and what it exposes) rather than behaviour.
    """
    keep, depth = [], 0
    for ln in snippet.splitlines():
        s = ln.strip()
        if not s or s.startswith("//") or s.startswith("*") or s.startswith("/*"):
            continue
        if depth <= 1 and (
                s.startswith(("package ", "import ", "public ", "protected ", "private ",
                              "abstract ", "final ", "static ", "class ", "interface ",
                              "enum ", "record ", "@"))):
            keep.append(s[:160])
        depth += ln.count("{") - ln.count("}")
        if len(keep) >= max_lines:
            break
    return keep


def load_refactorings(rminer_dir: Path, methods: Optional[set] = None
                      ) -> Iterable[tuple]:
    """(repo_stem, sha, refactoring) for every architectural refactoring on disk."""
    methods = methods or ARCHITECTURAL_METHODS
    for f in sorted(Path(rminer_dir).glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for commit in data.get("commits", []):
            sha = commit.get("sha1", "")
            for ref in commit.get("refactorings") or []:
                if ref.get("type") in methods:
                    yield f.stem, sha, ref


def build_example(repos_dir: Path, repo: str, sha: str, ref: Dict[str, Any]
                  ) -> Optional[Example]:
    """Extract one example, or None when the code cannot be read back."""
    repo_path = Path(repos_dir) / repo
    if not repo_path.is_dir():
        return None
    left = (ref.get("leftSideLocations") or [None])[0]
    right = (ref.get("rightSideLocations") or [None])[0]
    if not left or not right:
        return None

    before_src = git_show(repo_path, sha + "^", left.get("filePath", ""))
    after_src = git_show(repo_path, sha, right.get("filePath", ""))
    if not before_src or not after_src:
        return None

    method = ref["type"]
    b_snip = _slice(before_src, left.get("startLine", 1), left.get("endLine", 1))
    a_snip = _slice(after_src, right.get("startLine", 1), right.get("endLine", 1))
    return Example(
        repo=repo, sha=sha, method=method,
        candidate_smells=METHOD_TARGETS.get(method, []),
        before={"path": left.get("filePath"), "element": left.get("codeElement"),
                "type": left.get("codeElementType"),
                "signatures": _signature_only(b_snip),
                "lines": (left.get("endLine", 0) - left.get("startLine", 0)) + 1},
        after={"path": right.get("filePath"), "element": right.get("codeElement"),
               "signatures": _signature_only(a_snip),
               "lines": (right.get("endLine", 0) - right.get("startLine", 0)) + 1},
        context={"description": (ref.get("description") or "")[:300]},
    )


def build(rminer_dir: Path, repos_dir: Path, per_method: int = 50,
          min_repos: int = 3, progress=None) -> Dict[str, Any]:
    """Collect up to `per_method` real examples for each architectural method.

    Spread across repositories on purpose: `min_repos` caps how many examples any single
    repository may contribute to one method, so a method is not learned from one project's
    house style. A method that cannot reach that spread is reported, not padded.
    """
    by_method: Dict[str, List[Example]] = collections.defaultdict(list)
    per_repo: Dict[tuple, int] = collections.Counter()
    seen, skipped = 0, collections.Counter()
    cap = max(1, per_method // max(1, min_repos))

    for repo, sha, ref in load_refactorings(rminer_dir):
        method = ref["type"]
        if len(by_method[method]) >= per_method:
            continue
        if per_repo[(method, repo)] >= cap:
            skipped["repo_cap"] += 1
            continue
        seen += 1
        ex = build_example(repos_dir, repo, sha, ref)
        if ex is None:
            skipped["unreadable"] += 1
            continue
        by_method[method].append(ex)
        per_repo[(method, repo)] += 1
        if progress and seen % 100 == 0:
            progress(seen, sum(len(v) for v in by_method.values()))

    return {
        "examples": {m: [e.as_dict() for e in v] for m, v in by_method.items() if v},
        "counts": {m: len(v) for m, v in sorted(by_method.items(),
                                                key=lambda kv: -len(kv[1])) if v},
        "repos_per_method": {m: len({e.repo for e in v}) for m, v in by_method.items() if v},
        "attempted": seen, "skipped": dict(skipped),
        "per_method_target": per_method, "repo_cap": cap,
    }
