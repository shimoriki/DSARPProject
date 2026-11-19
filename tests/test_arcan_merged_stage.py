"""Arcan sees ONE graph over all modules, not one graph per module (offline, hermetic).

Per-module runs cannot detect a smell that crosses modules; `_stage_classes` is what makes
the merged run possible, so what it must guarantee is that every module's classes arrive
under one root with nothing lost to a name collision.
"""
from pathlib import Path

from dsarp.tools.arcan_runner import _stage_classes


def _module(tmp: Path, name: str, pkg: str, cls: str) -> Path:
    """A module laid out the way Maven leaves it: <module>/target/classes/<pkg>/<cls>."""
    d = tmp / name / "target" / "classes" / pkg.replace(".", "/")
    d.mkdir(parents=True)
    (d / f"{cls}.class").write_bytes(b"\xca\xfe\xba\xbe")
    return tmp / name / "target" / "classes"


def test_every_module_reaches_one_root(tmp_path):
    dirs = [_module(tmp_path, "log4j-api", "org.apache.logging.log4j.spi", "Provider"),
            _module(tmp_path, "log4j-core", "org.apache.logging.log4j.core", "Logger")]
    stage = _stage_classes(dirs, tmp_path / "stage")

    assert len(list(stage.iterdir())) == 2
    # both modules' bytecode is under the single root Arcan will be pointed at
    assert {f.name for f in stage.rglob("*.class")} == {"Provider.class", "Logger.class"}


def test_same_named_modules_do_not_overwrite_each_other(tmp_path):
    """A nested reactor can hold two modules called `core`; merging them would silently
    drop one side's classes and undercount smells."""
    a = _module(tmp_path / "a", "core", "com.a", "Same")
    b = _module(tmp_path / "b", "core", "com.b", "Same")

    stage = _stage_classes([a, b], tmp_path / "stage")

    assert len(list(stage.iterdir())) == 2
    assert len(list(stage.rglob("Same.class"))) == 2


def test_restaging_does_not_accumulate(tmp_path):
    """The loop re-detects each pass into the same out_dir; leftovers from the previous
    pass would be counted as this pass's code."""
    a = _module(tmp_path, "mod-a", "com.a", "A")
    b = _module(tmp_path, "mod-b", "com.b", "B")
    stage = tmp_path / "stage"

    _stage_classes([a, b], stage)
    _stage_classes([a], stage)

    assert len(list(stage.iterdir())) == 1
    assert {f.name for f in stage.rglob("*.class")} == {"A.class"}
