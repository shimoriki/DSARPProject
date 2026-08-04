"""Addendum §7 — multi-repository dataset orchestration.

Iterates repositories in the requested splits, builds masked repo-independent rows,
and writes the multi-repo dataset artefacts. Cassandra/unseen repos are blocked from
any training split by the SplitManager leakage guard.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ..alignment.aligner import Alignment
from ..config import Config, load_repo_entries
from ..schemas import EvidenceCase
from ..splits.manager import SplitManager
from ..util import read_json
from .builder import DatasetBuilder


def _load_case(cfg: Config, project_id: str) -> EvidenceCase | None:
    data = read_json(cfg.data_dir / "normalized" / f"{project_id}.json")
    return EvidenceCase(**data) if data else None


def _load_alignments(cfg: Config, project_id: str) -> List[Alignment]:
    data = read_json(cfg.data_dir / "aligned_examples" / f"{project_id}.json", default=[]) or []
    return [Alignment(**a) for a in data]


def build_multi_repo_dataset(cfg: Config, splits: List[str] | None = None,
                             min_alignment: float = 0.5) -> Dict[str, Any]:
    splits = splits or ["train"]
    sm = SplitManager()
    sm.assert_no_leakage()  # refuse if configs are unsafe

    # truncate prior multi-repo artefacts so re-runs are idempotent
    for rel in ("training/multi_repo_train_candidates.jsonl",
                "training/multi_repo_train_instruct.jsonl",
                "training/multi_repo_train_chat.jsonl",
                "validation/multi_repo_validation_candidates.jsonl"):
        f = cfg.data_dir / rel
        if f.exists():
            f.unlink()

    train_builder = DatasetBuilder(cfg.data_dir / "training", min_alignment)
    val_builder = DatasetBuilder(cfg.data_dir / "validation", min_alignment)

    train_rows: List[Dict[str, Any]] = []
    val_rows: List[Dict[str, Any]] = []
    alignments_by_repo: Dict[str, List[Alignment]] = {}
    skipped: List[str] = []

    for split in splits:
        for entry in load_repo_entries(split):
            pid = entry["project_id"]
            if split in ("train", "validation") and not sm.is_training_allowed(pid):
                skipped.append(pid)  # leakage guard
                continue
            case = _load_case(cfg, pid)
            if case is None:
                continue
            aligns = _load_alignments(cfg, pid)
            alignments_by_repo[pid] = aligns
            builder = train_builder if split == "train" else val_builder
            for smell in case.smells:
                rows = builder.build_ranker_rows(pid, split, smell,
                                                 case.dependency_graph, aligns)
                if split == "train":
                    train_rows.extend(rows)
                    train_builder.write_candidates(rows, "multi_repo_train_candidates.jsonl")
                    best = max((r for r in rows), key=lambda r: r["alignment_confidence"],
                               default=None)
                    if best:
                        train_builder.write_instruct(smell, pid, best["refactoring_type"])
                        train_builder.write_chat(smell, pid,
                                                 f"Recommend {best['refactoring_type']} for "
                                                 f"{smell.smell_type}.")
                else:
                    val_rows.extend(rows)
                    val_builder.write_candidates(rows, "multi_repo_validation_candidates.jsonl")

    stats = train_builder.stats(train_rows) if train_rows else {"examples": 0}
    train_builder.write_stats(train_rows)
    train_builder.write_alignment_report(alignments_by_repo)
    return {"train_examples": len(train_rows), "validation_examples": len(val_rows),
            "stats": stats, "skipped_leakage": skipped,
            "outputs": {
                "train_candidates": str(cfg.data_dir / "training" / "multi_repo_train_candidates.jsonl"),
                "validation_candidates": str(cfg.data_dir / "validation" / "multi_repo_validation_candidates.jsonl"),
                "stats": str(cfg.data_dir / "reports" / "multi_repo_dataset_stats.json"),
                "alignment_report": str(cfg.data_dir / "reports" / "multi_repo_alignment_report.csv"),
            }}
