"""Multi-repository generalisation + backend tests (offline, hermetic)."""
import json
from pathlib import Path

import jsonschema
import pytest

from dsarp.config import load_config
from dsarp.features.extractor import FeatureExtractor, NameMasker, FEATURE_ORDER
from dsarp.schemas import DependencyGraph, Smell
from dsarp.graphs.builder import DependencyGraphBuilder
from dsarp.splits.manager import SplitManager
from dsarp.source_index.indexer import SourceIndexer

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "docs" / "schemas"
MINI_REPO = ROOT / "data" / "samples" / "mini-java-repo"


# --- leakage / splits ----------------------------------------------------- #
def test_heldout_repos_blocked_from_training():
    """EXPERIMENT: Cassandra is now a training repo; the held-out TEST (log4j2) and
    the random UNSEEN repo (commons-validator) must stay out of training."""
    sm = SplitManager()
    assert sm.is_training_allowed("apache-tika") is True
    for held in sm.test + sm.unseen:  # fixed test + random unseen
        assert sm.is_training_allowed(held) is False


def test_no_leakage_current_configs():
    SplitManager().assert_no_leakage()  # must not raise


def test_test_repo_not_in_training():
    sm = SplitManager()
    assert not (set(sm.test) & set(sm.train))
    assert not (set(sm.unseen) & set(sm.train))


def test_loro_folds_exclude_heldout():
    sm = SplitManager()
    folds = sm.loro_folds(["r1", "r2", "r3"])
    assert len(folds) == 3
    for f in folds:
        assert f.held_out not in f.train
        assert len(f.train) == 2


def test_loro_folds_drop_heldout():
    """A held-out test/unseen repo must never appear as a LORO training fold."""
    sm = SplitManager()
    held_repo = (sm.test or sm.unseen or ["apache-logging-log4j2"])[0]
    folds = sm.loro_folds(["apache-tika", held_repo])
    held = {f.held_out for f in folds}
    assert held_repo not in held  # blocked from training


# --- masking / repo-independent features ---------------------------------- #
def test_name_masking_roundtrip():
    m = NameMasker(["org.apache.tika.parser", "org.apache.tika.detect"])
    masked = m.mask("org.apache.tika.parser depends on org.apache.tika.detect")
    assert "Component_A" in masked and "Component_B" in masked
    assert "tika" not in masked
    assert m.unmask(masked) == "org.apache.tika.parser depends on org.apache.tika.detect"


def test_features_are_name_independent():
    """Same structure, different package names -> identical feature vectors."""
    fx = FeatureExtractor()
    gA = DependencyGraphBuilder().build([{"source": "a.x", "target": "a.y", "weight": 2},
                                         {"source": "a.y", "target": "a.x", "weight": 2}])
    gB = DependencyGraphBuilder().build([{"source": "zzz.p", "target": "zzz.q", "weight": 2},
                                         {"source": "zzz.q", "target": "zzz.p", "weight": 2}])
    sA = Smell(smell_id="s1", smell_type="Cyclic Dependency", affected_components=["a.x", "a.y"],
               tool_sources=["Arcan"], metrics={"cycle_length": 2}, severity="high")
    sB = Smell(smell_id="s2", smell_type="Cyclic Dependency", affected_components=["zzz.p", "zzz.q"],
               tool_sources=["Arcan"], metrics={"cycle_length": 2}, severity="high")

    class C:
        recommended_refactoring = "Extract Interface"; refactoring_type = "Extract Interface"
        graph_delta_estimate = 0.7; risk_score = 0.2; recipe_applicable = True
        requires_source_inspection = True; catalogue_rank = 1.0
    fa = fx.extract(sA, C(), gA)
    fb = fx.extract(sB, C(), gB)
    assert [fa[k] for k in FEATURE_ORDER] == [fb[k] for k in FEATURE_ORDER]


# --- source index --------------------------------------------------------- #
def test_source_indexer_finds_classes():
    idx = SourceIndexer().index("mini-java", MINI_REPO)
    assert idx.file_count == 2
    assert "com.example.alpha.Alpha" in idx.classes
    assert "com.example.alpha" in idx.packages
    assert idx.import_edges  # alpha<->beta imports


# --- multi-repo dataset stats --------------------------------------------- #
def test_multi_repo_dataset_stats(tmp_path):
    from dsarp.dataset.builder import DatasetBuilder
    from dsarp.alignment.aligner import Alignment
    b = DatasetBuilder(tmp_path / "training")
    g = DependencyGraphBuilder().build([{"source": "a.x", "target": "a.y"},
                                        {"source": "a.y", "target": "a.x"}])
    s = Smell(smell_id="s1", smell_type="Cyclic Dependency", affected_components=["a.x", "a.y"],
              tool_sources=["Arcan"], severity="high")
    aligns = [Alignment(smell_id="s1", smell_type="Cyclic Dependency", event_id="e",
                        refactoring_type="Extract Interface", alignment_confidence=0.9)]
    rows = b.build_ranker_rows("repoA", "train", s, g, aligns)
    assert rows and all(r["project_id"] == "repoA" for r in rows)
    stats = b.stats(rows)
    assert stats["repositories"] == 1 and stats["positive"] >= 1


# --- unseen repo inference ------------------------------------------------ #
def test_unseen_repo_inference_schema_valid(tmp_path):
    from dsarp.inference.unseen import evaluate_unseen_repo
    cfg = load_config("local", overrides={"data_dir": str(tmp_path),
                                          "model_provider": {"type": "offline"}})
    cfg.data_dir = tmp_path
    sugs, report = evaluate_unseen_repo(cfg, "mini-java", repo_path=MINI_REPO, top_k=2)
    assert report["preparation"]["build_system"] == "plain-java"  # no pom.xml at root
    assert "Arcan" in report["preparation"]["tools_unavailable"]
    schema = json.loads((SCHEMAS / "suggestion_schema.json").read_text())
    for s in sugs:
        jsonschema.validate(s.to_contract_dict(), schema)


# --- DB roundtrip --------------------------------------------------------- #
def test_db_roundtrip(tmp_path):
    from dsarp.db import Store
    store = Store(tmp_path / "t.sqlite")
    store.init()
    store.save_repository(project_id="p1", revision="r1")
    store.save_suggestions([{"suggestion_id": "sug1", "project_id": "p1", "rank": 1,
                             "score": 0.5, "smell_type": "Cyclic Dependency",
                             "openrewrite_recipe_plan": {"recipe_status": "draft"}}])
    assert len(store.list_suggestions("p1")) == 1
    assert store.status()["row_counts"]["suggestions"] == 1


# --- examples validate ---------------------------------------------------- #
@pytest.mark.parametrize("example,schema", [
    ("suggestion.example.json", "suggestion_schema.json"),
    ("context_package.example.json", "context_package_schema.json"),
    ("hgrs_review.example.json", "hgrs_review_schema.json"),
])
def test_examples_validate(example, schema):
    ex_path = ROOT / "examples" / example
    sc_path = SCHEMAS / schema
    if not ex_path.exists() or not sc_path.exists():
        pytest.skip("example or schema missing")
    jsonschema.validate(json.loads(ex_path.read_text()), json.loads(sc_path.read_text()))


# --- lora guard ----------------------------------------------------------- #
def test_lora_guard_blocks_small(tmp_path):
    from dsarp.training.lora import lora_train
    cfg = load_config("local", overrides={"data_dir": str(tmp_path)})
    cfg.data_dir = tmp_path
    res = lora_train(cfg, dry_run=True)
    assert res["status"] in ("too_few_examples", "planned")


# --- real-repo weak supervision ------------------------------------------ #
def test_weak_aligner_produces_both_classes():
    """Weak labels from a real cycle must yield positives AND negatives (not all-positive)."""
    from dsarp.alignment.weak import GraphWeakAligner
    from dsarp.dataset.builder import DatasetBuilder
    from pathlib import Path
    import tempfile
    g = DependencyGraphBuilder().build([{"source": "a.x", "target": "a.y"},
                                        {"source": "a.y", "target": "a.x"}])
    s = Smell(smell_id="s1", smell_type="Cyclic Dependency", affected_components=["a.x", "a.y"],
              tool_sources=["DependencyGraph"], metrics={"cycle_length": 2}, severity="high")
    aligns = GraphWeakAligner().align([s], g)
    assert aligns and all(0 < a.alignment_confidence <= 0.6 for a in aligns)  # capped weak
    with tempfile.TemporaryDirectory() as td:
        rows = DatasetBuilder(Path(td)).build_ranker_rows("repoR", "train", s, g, aligns)
    labels = {r["label"] for r in rows}
    assert labels == {0, 1}, "weak supervision must yield both positive and negative labels"


def test_weak_aligner_blocks_nonstructural():
    """No graph support => no weak alignment (never fabricate)."""
    from dsarp.alignment.weak import GraphWeakAligner
    g = DependencyGraphBuilder().build([{"source": "a.x", "target": "a.y"}])  # no cycle
    s = Smell(smell_id="s2", smell_type="Cyclic Dependency", affected_components=["a.x", "a.y"],
              tool_sources=["Arcan"], severity="high")  # claims cyclic but graph has no cycle
    aligns = GraphWeakAligner().align([s], g)
    assert aligns == []  # no real cycle => no weak label


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
