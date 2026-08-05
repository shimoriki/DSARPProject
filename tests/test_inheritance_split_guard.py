"""Two individually safe moves must not separate a subclass from its superclass.

commons-validator pass 3 failed to compile because LuhnCheckDigit and ModulusCheckDigit
started in routines.checkdigit and were sent to validator.digit and validator by two
different plans. Each plan passed its own preconditions; the combination did not, and
nothing looked at the combination.
"""
from dsarp.verification.openrewrite_loop import (
    inheritance_pairs, splits_an_inheritance_pair)


def _repo(tmp_path):
    pkg = tmp_path / "src/main/java/org/apache/commons/validator/routines/checkdigit"
    pkg.mkdir(parents=True)
    (pkg / "ModulusCheckDigit.java").write_text(
        "package org.apache.commons.validator.routines.checkdigit;\n"
        "public class ModulusCheckDigit {\n  ModulusCheckDigit(int m) {}\n}\n",
        encoding="utf-8")
    (pkg / "LuhnCheckDigit.java").write_text(
        "package org.apache.commons.validator.routines.checkdigit;\n"
        "public class LuhnCheckDigit extends ModulusCheckDigit {\n"
        "  public LuhnCheckDigit() { super(10); }\n}\n", encoding="utf-8")
    return tmp_path


BASE = "org.apache.commons.validator.routines.checkdigit"


def test_same_package_pair_is_found(tmp_path):
    pairs = inheritance_pairs(_repo(tmp_path))
    assert (f"{BASE}.LuhnCheckDigit", f"{BASE}.ModulusCheckDigit") in pairs


def test_splitting_the_pair_is_rejected(tmp_path):
    pairs = inheritance_pairs(_repo(tmp_path))
    already = {f"{BASE}.ModulusCheckDigit": "org.apache.commons.validator"}
    candidate = {f"{BASE}.LuhnCheckDigit": "org.apache.commons.validator.digit"}
    assert splits_an_inheritance_pair(pairs, already, candidate) is not None


def test_moving_the_pair_together_is_allowed(tmp_path):
    pairs = inheritance_pairs(_repo(tmp_path))
    both = {BASE + ".*": "org.apache.commons.validator"}
    assert splits_an_inheritance_pair(pairs, {}, both) is None


def test_unrelated_move_is_allowed(tmp_path):
    pairs = inheritance_pairs(_repo(tmp_path))
    candidate = {"org.apache.commons.validator.other.Thing": "org.apache.commons.validator"}
    assert splits_an_inheritance_pair(pairs, {}, candidate) is None
