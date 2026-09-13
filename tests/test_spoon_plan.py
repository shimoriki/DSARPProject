"""The model's edit plan is checked against real source before Spoon runs.

Every case here is a way a language model actually fails on this task: naming a class that
does not exist, inventing a tidy-sounding target package, proposing an op the driver does
not implement, or moving a type across a Maven module boundary because the architecture
argument was sound and the build was not its problem.
"""
import tempfile
from pathlib import Path

from dsarp.agents.spoon_refactor import verdict
from dsarp.refactoring import spoon_plan
from dsarp.refactoring.strategies import SourceFacts


def _repo() -> Path:
    """Two packages in one module, plus a third in a second module."""
    root = Path(tempfile.mkdtemp(prefix="spoon-test-"))
    files = {
        "mod-a/src/main/java/com/x/core/Engine.java":
            "package com.x.core;\npublic class Engine { }\n",
        "mod-a/src/main/java/com/x/core/Nested.java":
            "package com.x.core;\npublic class Nested {\n    public class Inner { }\n}\n",
        "mod-a/src/main/java/com/x/util/Helper.java":
            "package com.x.util;\npublic class Helper { }\n",
        "mod-b/src/main/java/com/x/api/Facade.java":
            "package com.x.api;\npublic class Facade { }\n",
    }
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


def _plan(*edits):
    import json
    return spoon_plan.parse(json.dumps({"reasoning": "t", "edits": list(edits)}))


def test_allowlist_rejects_unimplemented_ops():
    p = _plan({"op": "extractMethod", "type": "com.x.core.Engine", "toPackage": "com.x.util"})
    assert p.edits == []
    assert "not implemented" in p.rejected[0]["why"]


def test_validation_against_real_source():
    facts = SourceFacts(_repo())

    ok = spoon_plan.validate(
        _plan({"op": "moveClass", "type": "com.x.core.Engine", "toPackage": "com.x.util"}), facts)
    assert len(ok.edits) == 1 and not ok.rejection

    def why(**edit):
        return spoon_plan.validate(_plan({"op": "moveClass", **edit}), facts).rejected[0]["why"]

    # a class the model made up
    assert "not a type in this repository" in why(
        type="com.x.core.Imaginary", toPackage="com.x.util")
    # a target package that sounds right and does not exist
    assert "does not exist" in why(type="com.x.core.Engine", toPackage="com.x.core.internal")
    # nested types are not top-level files; Spoon cannot relocate one on its own
    assert "nested type" in why(type="com.x.core.Nested.Inner", toPackage="com.x.util")
    # architecturally defensible, breaks the build
    assert "cross-module" in why(type="com.x.core.Engine", toPackage="com.x.api")


def test_source_roots_are_the_ones_the_edits_touch():
    repo = _repo()
    facts = SourceFacts(repo)
    p = spoon_plan.validate(
        _plan({"op": "moveClass", "type": "com.x.core.Engine", "toPackage": "com.x.util"}), facts)
    roots = spoon_plan.source_roots_for(p, facts)
    assert len(roots) == 1 and roots[0].endswith(str(Path("mod-a/src/main/java")))


def test_verdict_puts_compile_before_smell_count():
    broken = {"compile": {"status": "failed"}, "measured": True, "smells": 1}
    assert verdict({"smells": 10}, broken) == "rejected_build_broken"

    good = {"compile": {"status": "compiled"}, "measured": True, "smells": 8}
    assert verdict({"smells": 10}, good) == "kept_smells_reduced"
    assert verdict({"smells": 8}, good) == "rejected_no_reduction"
    assert verdict({"smells": 5}, good) == "rejected_smells_increased"


def test_skill_is_the_system_prompt():
    """The instructions the model gets are the skill file, not a second copy that can drift."""
    prompt = spoon_plan.system_prompt()
    assert prompt.startswith("#")
    assert "---" not in prompt.splitlines()[0]      # frontmatter stripped
    # The contract is picking a number, not authoring an edit.
    assert '"pick"' in prompt


def test_candidates_are_applicable_by_construction():
    """The model can no longer produce an inapplicable plan — only an unhelpful one.

    Every enumerated candidate has already passed the same check validate() applies, so a
    pick cannot be a hallucinated class, a same-package move, or a cross-module move.
    """
    from dsarp.agents.spoon_refactor import candidate_edits, parse_picks
    # A real cross-package reference, which is what makes a move candidate exist at all.
    root = _repo()
    (root / "mod-a/src/main/java/com/x/core/Bridge.java").write_text(
        "package com.x.core;\nimport com.x.util.Helper;\n"
        "public class Bridge { Helper h; }\n", encoding="utf-8")
    facts = SourceFacts(root)
    finding = {"smell_type": "Cyclic Dependency",
               "components": ["com.x.core", "com.x.util"]}

    cands = candidate_edits(facts, finding)
    assert cands, "Bridge sits in com.x.core and references com.x.util — that is a move"
    for e in cands:
        assert not spoon_plan._why_not(e, facts), f"enumerated an illegal move: {e}"

    picked = parse_picks('{"pick": [1], "reasoning": "r"}', cands)
    assert picked.edits == [cands[0]]
    # A number the model made up is recorded, not silently dropped.
    bad = parse_picks('{"pick": [99]}', cands)
    assert not bad.edits and "outside 1.." in bad.rejected[0]["why"]


def test_source_root_is_layout_independent():
    """Gradle source sets and flat src/ layouts must resolve too, not just Maven's."""
    import tempfile as _t
    root = Path(_t.mkdtemp(prefix="layout-"))
    f = root / "app" / "src" / "debug" / "kotlinjava" / "com" / "y" / "A.java"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("package com.y;\npublic class A { }\n", encoding="utf-8")
    facts = SourceFacts(root)
    assert spoon_plan.source_root_of(facts, "com.y.A") == f.parents[2]


def test_single_package_smell_gets_siblings_not_itself():
    """Hub-like Dependency, God Component and Unstable Dependency each name ONE package.

    Offering that package back as the target asks for a move into the package the type is
    already in, which validate() rejects — so the finding burns a model call and can never
    produce an edit. Siblings are the only legal targets.
    """
    from dsarp.agents.spoon_refactor import candidate_targets
    facts = SourceFacts(_repo())

    single = candidate_targets(facts, ["com.x.core"])
    assert "com.x.core" not in single, "the affected package is the source, never a target"
    assert single == ["com.x.util"]

    # A cycle names several packages; those ARE the targets.
    assert candidate_targets(facts, ["com.x.core", "com.x.util"]) == ["com.x.core", "com.x.util"]
    # Nothing to offer is reported as nothing, not as the source package.
    assert candidate_targets(facts, ["com.nonexistent"]) == []


def test_exemplars_parse_real_moves_and_drop_same_package_renames():
    import json as _json
    from dsarp.refactoring import exemplars
    d = Path(tempfile.mkdtemp(prefix="rminer-"))
    (d / "proj.json").write_text(_json.dumps({"commits": [{"refactorings": [
        {"type": "Move Class", "description": "Move Class a.b.C moved to x.y.C"},
        {"type": "Move And Rename Class", "description": "Move And Rename Class a.b.D moved to x.y.E"},
        # same package: a rename, useless as an example of where a type belongs
        {"type": "Move Class", "description": "Move Class a.b.F moved to a.b.G"},
        {"type": "Extract Method", "description": "Extract Method something"},
    ]}]}), encoding="utf-8")

    moves = exemplars.load(d)
    assert len(moves) == 3, "Extract Method is not a package move"
    block = exemplars.as_prompt_block(moves, k=6)
    assert "a.b.C  ->  x.y.C" in block
    assert "a.b.F" not in block, "same-package rename should not be shown as a move"


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_"):
            fn()
    print("ok")


def test_reasoning_model_think_block_is_stripped():
    """qwen3 and deepseek-r1 emit <think> before answering.

    The scratch work contains braces, so a naive brace search returns the model's reasoning
    instead of its answer — the pick silently becomes garbage rather than failing loudly.
    """
    from dsarp.agents.spoon_refactor import parse_picks
    cands = [spoon_plan.Edit("moveClass", "a.B", "a.c"),
             spoon_plan.Edit("moveClass", "a.D", "a.c")]

    raw = ('<think>Maybe {"pick": [99]} would work, but no.</think>'
           '{"pick": [2], "reasoning": "breaks the edge"}')
    p = parse_picks(raw, cands)
    assert [e.type for e in p.edits] == ["a.D"], p.rejection
    assert not p.rejected, "the brace inside <think> must not be read as an answer"


def test_environmental_build_failure_is_not_blamed_on_the_refactoring():
    """A whole 8-arm model sweep came back `rejected_build_broken` with ZERO javac errors.

    log4j2's reactor wants an artifact that is not in the local repository; the build dies
    before compiling anything. Calling that "the refactoring broke the build" manufactures a
    false negative for every arm, including a control arm that used no model at all.
    """
    from dsarp.tools.arcan_runner import _failure_kind

    resolution = ("[ERROR] Failed to execute goal on project log4j-core-fuzz-test: "
                  "Could not resolve dependencies\n[ERROR] Could not find artifact "
                  "org.apache.logging.log4j:log4j-fuzz-test:jar:2.27.0-SNAPSHOT")
    assert _failure_kind(resolution, 1) == "dependency_unresolved"
    assert verdict({"smells": 677},
                   {"compile": {"status": "dependency_unresolved"}, "measured": True,
                    "smells": 66}) == "inconclusive_dependency_unresolved"

    # A real compilation error still blames the change, as it should.
    broke = "[ERROR] /src/A.java:[10,5] cannot find symbol"
    assert _failure_kind(broke, 1) == "compile_failed"
    assert verdict({"smells": 677},
                   {"compile": {"status": "compile_failed"}}) == "rejected_build_broken"

    # 0xC0000142 with no output is a JVM that never started, not a broken source tree.
    assert _failure_kind("\n", 3221225794) == "jvm_start_failed"


def test_excluding_the_refactored_module_is_not_a_pass():
    """compile_repo drops modules it cannot build and reports success on the rest.

    On log4j2 that excluded log4j-core — which had received six of seven moves — and
    returned status "compiled" with 36 class dirs against a 37-dir baseline. A module the
    refactoring broke is a broken refactoring, and a smell delta across different module
    sets measures nothing.
    """
    base = {"smells": 677, "compile": {"status": "compiled", "excluded_modules": []}}
    after = {"smells": 400, "measured": True,
             "compile": {"status": "compiled", "excluded_modules": ["log4j-core"]}}
    assert verdict(base, after) == "rejected_module_excluded:log4j-core"

    # A module BOTH sides dropped is a pre-existing gap, not something the change caused.
    base2 = {"smells": 677, "compile": {"status": "compiled", "excluded_modules": ["flaky"]}}
    after2 = {"smells": 600, "measured": True,
              "compile": {"status": "compiled", "excluded_modules": ["flaky"]}}
    assert verdict(base2, after2) == "kept_smells_reduced"


def test_package_private_type_cannot_leave_its_package():
    """move_blockers() asks what the moving class needs FROM its package. Nothing asked the
    mirror question — what the package needs FROM it.

    log4j-core failed on exactly this: AbstractAsyncExceptionHandler has no `public`
    modifier, and moving it out of core.async left two siblings with
    "is not public in ...; cannot be accessed from outside package".
    """
    root = Path(tempfile.mkdtemp(prefix="pkgpriv-"))
    files = {
        # no `public` modifier — visible only inside com.x.core
        "src/main/java/com/x/core/Hidden.java":
            "package com.x.core;\n\nabstract class Hidden { }\n",
        "src/main/java/com/x/core/User.java":
            "package com.x.core;\n\npublic class User extends Hidden { }\n",
        # public, and nobody in the package uses it: free to move
        "src/main/java/com/x/core/Loose.java":
            "package com.x.core;\n\npublic class Loose { }\n",
        "src/main/java/com/x/util/Helper.java":
            "package com.x.util;\n\npublic class Helper { }\n",
    }
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    facts = SourceFacts(root)

    why = spoon_plan._why_not(
        spoon_plan.Edit("moveClass", "com.x.core.Hidden", "com.x.util"), facts)
    assert "package-private" in why and "still use it" in why

    assert not spoon_plan._why_not(
        spoon_plan.Edit("moveClass", "com.x.core.Loose", "com.x.util"), facts)


def test_stale_precomputed_findings_fall_through_to_live_detection():
    """A file that exists but holds almost nothing is worse than no file at all.

    apache-tika.json carries ONE finding while the same commit's predictions list 261 cyclic
    dependencies. Treating "present" as "usable" silently reduced a whole Tika run to that
    single finding — and unlike a missing file, nothing about it looked wrong.
    """
    import json as _json
    from dsarp.agents.spoon_refactor import arcan_findings
    d = Path(tempfile.mkdtemp(prefix="stale-"))
    (d / "raw" / "arcan").mkdir(parents=True)
    (d / "raw" / "arcan" / "p.json").write_text(_json.dumps(
        [{"smell_type": "Cyclic Dependency", "affected_components": ["a", "b"],
          "evidence_id": "E1"}]), encoding="utf-8")

    # No repo to detect against: the single stored finding is still returned, not dropped.
    assert len(arcan_findings(d, "p")) == 1
    # A healthy file is used as-is.
    (d / "raw" / "arcan" / "q.json").write_text(_json.dumps(
        [{"smell_type": "X", "affected_components": ["a"], "evidence_id": "E1"},
         {"smell_type": "Y", "affected_components": ["b"], "evidence_id": "E2"}]),
        encoding="utf-8")
    assert len(arcan_findings(d, "q")) == 2
