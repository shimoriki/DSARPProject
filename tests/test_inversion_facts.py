"""Inversion blockers, judged against packages after a state's moves."""
from dsarp.refactoring.inversion_facts import InversionFacts
from dsarp.refactoring.strategies import SourceFacts

IMPL = ("package q;\nimport r.Foo;\npublic class Impl {\n    public Impl(int n) {}\n"
        "    public Foo get(Bar b) { return null; }\n    public static Baz make() { return null; }\n"
        "    public void run() {}\n}\n")


def _repo(tmp_path, extra=()):
    files = {"m/src/main/java/q/Impl.java": IMPL,
             "m/src/main/java/q/Bar.java": "package q;\npublic class Bar {}\n",
             "m/src/main/java/q/Baz.java": "package q;\npublic class Baz {}\n",
             "m/src/main/java/r/Foo.java": "package r;\npublic class Foo {}\n",
             "m/src/main/java/p/User.java": "package p;\npublic class User {}\n",
             "m/src/main/java/q/Api.java": "package q;\npublic interface Api { void x(); }\n",
             **dict(extra)}
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return SourceFacts(tmp_path)


def _snap(constructs=(), kinds=("has type",)):
    return {"edges": [{"from": "p", "to": "q", "constructs": list(constructs), "kinds": list(kinds)}]}


def test_construction_blocks_until_the_builder_moves_out(tmp_path):
    f = InversionFacts(_snap(["p.Maker -> q.Impl"]), _repo(tmp_path))
    assert "p.Maker" in f.blocked("p", "q.Impl", {})
    assert f.blocked("p", "q.Impl", {"p.Maker": "r"}) is None


def test_a_builder_moved_into_the_consumer_blocks(tmp_path):
    f = InversionFacts(_snap(["r.Maker -> q.Impl$Inner"]), _repo(tmp_path))
    assert f.blocked("p", "q.Impl", {}) is None
    assert f.blocked("p", "q.Impl", {"r.Maker": "p"})


def test_other_source_root_is_blocked(tmp_path):
    facts = _repo(tmp_path, {"n/src/main/java/s/Far.java": "package s;\npublic class Far {}\n"})
    assert "source roots" in InversionFacts(_snap(), facts).blocked("s", "q.Impl", {})


def test_interfaces_and_declares_nothing_are_blocked(tmp_path):
    facts = _repo(tmp_path)
    assert InversionFacts(_snap(), facts).blocked("p", "q.Api", {}) == "already an interface"
    assert "declares nothing" in InversionFacts(_snap(kinds=["calls method"]), facts).blocked("p", "q.Impl", {})


def test_nested_targets_fold_to_their_owner(tmp_path):
    f = InversionFacts(_snap(), _repo(tmp_path))
    assert f.candidates({("p.User", "q.Impl"), ("q.Impl", "q.Bar"), ("x.Out", "q.Impl")}, {"p", "q"}) \
        == [("p", "q.Impl")]


def test_signature_types_resolve_imports_and_own_package(tmp_path):
    # Constructors and statics are not on an interface; Foo comes by import, Bar by package.
    assert InversionFacts(_snap(), _repo(tmp_path)).signature_types("q.Impl") == {"r.Foo", "q.Bar"}
