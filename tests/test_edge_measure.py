"""The packaged experiment driver must find what changed and write a readable patch.

These were the parts most likely to rot unnoticed in the scratch version: the diff was empty
for every patch it wrote, because the working copy has no .git and `git diff` inside one
compares nothing.
"""
from dsarp.experiments.edge_measure import _changed_java, write_patch


def _tree(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


ROW = {"type": "com.app.Thing", "to_package": "com.app.core",
       "success_criterion": "the bytecode edge a -> b no longer exists",
       "structural": {"edges_removed": 3, "edges_added": []},
       "tests": {"tests_run": 2050, "failures": 0, "errors": 0}}


def test_modified_added_and_removed_files_are_all_detected(tmp_path):
    before = _tree(tmp_path / "before", {
        "src/A.java": "class A {}\n", "src/Gone.java": "class Gone {}\n"})
    after = _tree(tmp_path / "after", {
        "src/A.java": "class A { int x; }\n", "src/New.java": "class New {}\n"})
    names = sorted(p.name for p in _changed_java(before, after))
    assert names == ["A.java", "Gone.java", "New.java"]


def test_build_output_is_not_mistaken_for_a_change(tmp_path):
    before = _tree(tmp_path / "before", {"src/A.java": "class A {}\n"})
    after = _tree(tmp_path / "after", {"src/A.java": "class A {}\n",
                                       "target/generated/A.java": "class A {}\n"})
    assert _changed_java(before, after) == []


def test_a_patch_carries_the_measurement_and_a_real_diff(tmp_path):
    before = _tree(tmp_path / "before", {"src/A.java": "class A {}\n"})
    after = _tree(tmp_path / "after", {"src/A.java": "class A { int x; }\n"})
    p = write_patch(before, after, tmp_path / "patches", ROW)
    text = p.read_text(encoding="utf-8")
    assert "3 package edges removed, 0 added" in text and "2050 tests run" in text
    assert "--- a/src/A.java" in text and "+class A { int x; }" in text


def test_a_patch_needing_manual_fixup_says_so_in_its_header(tmp_path):
    before = _tree(tmp_path / "before", {"src/A.java": "class A {}\n"})
    after = _tree(tmp_path / "after", {"src/A.java": "class B {}\n"})
    row = dict(ROW, before_apply={"ok": False, "why": "1 file names this class as text"})
    text = write_patch(before, after, tmp_path / "patches", row).read_text(encoding="utf-8")
    assert "# REVIEW: 1 file names this class as text" in text
