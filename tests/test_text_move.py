"""The text engine moves a class and leaves every other byte alone."""
from pathlib import Path

from dsarp.refactoring.text_move import move_classes


def _write(root: Path, rel: str, data: bytes) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_bytes_survive_and_former_siblings_resolve(tmp_path):
    src = tmp_path / "src/main/java"
    body = ("package a.b;\r\n\r\npublic class Moved {\r\n"
            "  String s = \"…￾\";\r\n  Helper h;\r\n}\r\n").encode("utf-8") + b"// \xe9\r\n"
    _write(src, "a/b/Moved.java", body)
    _write(src, "a/b/Helper.java", b"package a.b;\n\nclass Helper { Moved m; }\n")
    _write(src, "a/x/User.java", b"package a.x;\n\nimport a.b.*;\n\nclass User { Moved m; }\n")

    assert move_classes(tmp_path, [(str(src), "a.b.Moved", "a.c")])["applied"]

    moved = (src / "a/c/Moved.java").read_bytes()
    assert not (src / "a/b/Moved.java").exists()
    assert moved == body.replace(b"package a.b;\r\n", b"package a.c;\r\nimport a.b.Helper;\r\n")
    assert b"import a.c.Moved;" in (src / "a/b/Helper.java").read_bytes()
    assert b"import a.c.Moved;" in (src / "a/x/User.java").read_bytes()


def test_a_sibling_moved_elsewhere_is_imported_from_where_it_went(tmp_path):
    src = tmp_path / "src/main/java"
    _write(src, "a/b/One.java", b"package a.b;\n\nclass One { Two t; }\n")
    _write(src, "a/b/Two.java", b"package a.b;\n\nclass Two { One o; }\n")

    moves = [(str(src), "a.b.One", "a.c"), (str(src), "a.b.Two", "a.d")]
    assert move_classes(tmp_path, moves)["applied"]

    assert b"import a.d.Two;" in (src / "a/c/One.java").read_bytes()
    assert b"import a.c.One;" in (src / "a/d/Two.java").read_bytes()


def test_a_secondary_type_is_refused_not_guessed(tmp_path):
    src = tmp_path / "src/main/java"
    _write(src, "a/b/Host.java", b"package a.b;\n\nclass Host {}\nclass Tail {}\n")

    assert not move_classes(tmp_path, [(str(src), "a.b.Tail", "a.c")])["applied"]
