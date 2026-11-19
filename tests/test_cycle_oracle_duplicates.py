"""A class compiled into two modules must not make the cycle oracle's answer depend on where the
working copy lives.

Log4j2 has org.apache.logging.log4j.util.internal.SerializationUtil twice: the real one in
log4j-api (it uses util and status, which closes a cycle) and a stub in log4j-api-java9. ArchUnit
kept one or the other depending on the copy's absolute path, so the same class files gave a
49-package core cycle under beam_arcan/.../work/copy and 50 under agentic/.../work/copy, and the
structural gate failed two AI plans for "a new cycle" that no move had made.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from dsarp.tools import archunit_runner as au

JAVAC = shutil.which("javac", path=str(Path(os.environ.get("JAVA_HOME", "")) / "bin")) or shutil.which("javac")
pytestmark = pytest.mark.skipif(not (JAVAC and au.oracle_built()), reason="needs javac and the oracle jar")


def _compile(src: dict, out: Path, cp: Path = None) -> None:
    tmp = out.parent / (out.parent.name + "-src")
    for rel, text in src.items():
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp / rel).write_text(text, encoding="utf-8")
    out.mkdir(parents=True, exist_ok=True)
    args = [JAVAC, "--release", "11", "-d", str(out)] + (["-cp", str(cp)] if cp else [])
    subprocess.run(args + [str(p) for p in tmp.rglob("*.java")], check=True, capture_output=True)


def _repo(root: Path) -> Path:
    # Module "a": p.Dup -> q.Q -> p.Dup, a real p <-> q cycle.
    _compile({"p/Dup.java": "package p; public class Dup { q.Q q; }",
              "q/Q.java": "package q; public class Q { p.Dup d; }"}, root / "a" / "target" / "classes")
    # Module "a-java9": the same p.Dup with no dependency, like log4j-api-java9's stub.
    _compile({"p/Dup.java": "package p; public class Dup { }"}, root / "a-java9" / "target" / "classes")
    return root


def test_duplicate_class_gives_the_same_cycles_wherever_the_copy_lives(tmp_path):
    answers = set()
    for name in ("beam_arcan", "agentic", "copy", "x", "work-copy", "zz", "arcan_repair", "m"):
        snap = au.cycles(_repo(tmp_path / name / "work" / "copy"))
        assert snap["ok"], snap
        answers.add(tuple(tuple(c) for c in snap["cycles"]))
    assert len(answers) == 1, answers


def test_first_class_dir_in_sorted_order_wins_and_the_duplicate_is_reported(tmp_path):
    snap = au.cycles(_repo(tmp_path / "r"))
    # "a-java9/..." sorts before "a/...", so its stub is the copy kept: no p <-> q cycle.
    assert snap["cycles"] == []
    assert snap["duplicateClasses"] == ["p.Dup"]
