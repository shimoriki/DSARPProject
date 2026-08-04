"""Build the EXPERIMENT training dataset: Cassandra in, Log4j2 out (it's the fixed test).

Efficient approach: reuse the existing RM-labeled rows for repos that are still trainable
(drops Log4j2, now the held-out test), then ADD Cassandra rows (weak-labelled from its
imported Arcan/Designite + structural smells; Cassandra is too big to mine with RM).
Cassandra smells are capped so its ~12k cyclic smells don't swamp the other repos.

Then trains the GBM ranker (leave-one-repository-out) on the new mix.

Usage: python scripts/build_experiment_dataset.py [--cassandra-cap 400] [--train]
"""
from __future__ import annotations

import argparse

import _bootstrap  # noqa: F401
from dsarp.alignment.weak import GraphWeakAligner
from dsarp.config import load_config
from dsarp.dataset.builder import DatasetBuilder
from dsarp.inference.unseen import prepare_evidence
from dsarp.schemas import EvidenceCase
from dsarp.splits.manager import SplitManager
from dsarp.training.ranker_trainer import RankerTrainer
from dsarp.util import append_jsonl, read_jsonl, read_json, write_json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="data/training/real_labeled_candidates.jsonl")
    ap.add_argument("--out", default="data/training/experiment_candidates.jsonl")
    ap.add_argument("--cassandra-cap", type=int, default=400,
                    help="max Cassandra smells to use (balance vs its ~12k cyclic smells)")
    ap.add_argument("--train", action="store_true")
    args = ap.parse_args()

    cfg = load_config("local")
    sm = SplitManager()
    sm.assert_no_leakage()
    out = cfg.data_dir / "training" / "experiment_candidates.jsonl"
    if out.exists():
        out.unlink()

    # 1) keep existing RM-labeled rows for still-trainable repos (drops Log4j2 = test)
    kept, dropped = 0, {}
    for r in read_jsonl(cfg.data_dir / "training" / "real_labeled_candidates.jsonl"):
        pid = r.get("project_id", "")
        if sm.is_training_allowed(pid):
            append_jsonl(out, r)
            kept += 1
        else:
            dropped[pid] = dropped.get(pid, 0) + 1
    print(f"[exp] kept {kept} RM-labelled rows; dropped (now held-out): {dropped}")

    # 2) add Cassandra (weak labels; capped)
    cass_dir = cfg.data_dir / "raw" / "repos" / "apache-cassandra"
    cass_rows = 0
    if cass_dir.exists() and any(cass_dir.rglob("*.java")):
        print("[exp] preparing Cassandra evidence (source index + graph + imported tools) ...")
        prepare_evidence(cfg, "apache-cassandra", repo_path=cass_dir)
        case = EvidenceCase(**read_json(cfg.data_dir / "normalized" / "apache-cassandra.json"))
        # cap: prioritise high-severity, multi-tool-confirmed smells
        smells = sorted(case.smells,
                        key=lambda s: ({"high": 3, "medium": 2, "low": 1}.get((s.severity or "medium").lower(), 2)
                                       + len(s.tool_sources)), reverse=True)[: args.cassandra_cap]
        aligner = GraphWeakAligner()
        aligns = aligner.align(smells, case.dependency_graph)
        builder = DatasetBuilder(cfg.data_dir / "training")
        rows = []
        for smell in smells:
            rows += builder.build_ranker_rows("apache-cassandra", "train", smell,
                                              case.dependency_graph, aligns)
        for r in rows:
            append_jsonl(out, r)
        cass_rows = len(rows)
        print(f"[exp] Cassandra: {len(case.smells)} total smells -> capped {len(smells)} "
              f"-> {cass_rows} rows (weak labels, no RM)")
    else:
        print("[exp] Cassandra source not present yet (clone still running?) — skipping its rows.")

    all_rows = list(read_jsonl(out))
    import collections
    by_repo = collections.Counter(r["project_id"] for r in all_rows)
    print(f"[exp] dataset: {len(all_rows)} rows across {len(by_repo)} repos -> {out}")
    print(f"[exp]   {dict(by_repo)}")
    write_json(cfg.data_dir / "reports" / "experiment_dataset_stats.json",
               {"total": len(all_rows), "by_repository": dict(by_repo),
                "cassandra_rows": cass_rows, "test_fixed": sm.test, "unseen_random": sm.unseen})

    if args.train and all_rows:
        trainer = RankerTrainer(cfg.data_dir / "models")
        res = trainer.train(out)
        m = res["metadata"]
        print(f"[exp] GBM ranker: {m['backend']} on {m['training_example_count']} rows "
              f"({len(m['training_repositories'])} repos)")
        loro = trainer.leave_one_repo_out(out)
        print(f"[exp] LORO mean={loro['mean_validation_score']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
