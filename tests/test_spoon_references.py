"""Every reference to a moved type has to follow it, or the build breaks.

These are the three shapes that actually failed on log4j-core after Spoon reported success:
an explicit import left pointing at the old package, a fully-qualified use, and — the one
that did the damage — a class left behind in the old package that used the moved type as a
bare sibling name and now needs an import it never had.
"""
import tempfile
from pathlib import Path

from dsarp.tools.spoon_runner import fix_references


def _repo(files):
    root = Path(tempfile.mkdtemp(prefix="refs-"))
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


def test_references_follow_a_moved_type():
    root = _repo({
        # imported explicitly from the old package
        "a/Importer.java":
            "package a;\n\nimport a.b.Moved;\n\npublic class Importer { Moved m; }\n",
        # uses the fully-qualified name
        "a/Qualified.java":
            "package a;\n\npublic class Qualified { a.b.Moved m; }\n",
        # sits in the OLD package and used the bare sibling name — no import existed
        "a/b/LeftBehind.java":
            "package a.b;\n\npublic class LeftBehind { Moved m; }\n",
    })
    moves = [{"type": "a.b.Moved", "toPackage": "a.c", "root": str(root), "newPath": ""}]
    res = fix_references(root, moves)

    imp = (root / "a/Importer.java").read_text(encoding="utf-8")
    assert "import a.c.Moved;" in imp and "import a.b.Moved;" not in imp

    qual = (root / "a/Qualified.java").read_text(encoding="utf-8")
    assert "a.c.Moved m;" in qual

    left = (root / "a/b/LeftBehind.java").read_text(encoding="utf-8")
    assert "import a.c.Moved;" in left, "a former sibling needs an import it never had"
    assert left.index("package a.b;") < left.index("import a.c.Moved;")
    assert res["imports_added"] == 1


def test_import_is_removed_when_the_type_lands_in_this_files_own_package():
    """pdfbox failed its build on code that compiled perfectly.

    CSArrayBased moved INTO org.apache.pdfbox.debugger, where PDFDebugger already lives, so
    rewriting its import produced a same-package import. javac accepts that; checkstyle
    reported four RedundantImport errors and failed the build.
    """
    root = _repo({
        "a/c/Neighbour.java":
            "package a.c;\n\nimport a.b.Moved;\n\npublic class Neighbour { Moved m; }\n"})
    fix_references(root, [{"type": "a.b.Moved", "toPackage": "a.c",
                           "root": str(root), "newPath": ""}])
    txt = (root / "a/c/Neighbour.java").read_text(encoding="utf-8")
    assert "import a.b.Moved;" not in txt, "stale import left behind"
    assert "import a.c.Moved;" not in txt, "same-package import is redundant; remove it"
    assert "Moved m;" in txt, "the usage itself must survive"
