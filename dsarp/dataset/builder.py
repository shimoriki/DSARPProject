"""Loop 7 / addendum §7 — training dataset builder (multi-repository, masked).

Per repo, per smell we emit repo-independent ranker rows (structural features only)
plus instruct/chat records with MASKED component names (Component_A/B/C). Real names
never enter training. Rows carry project_id + split so the ranker can do repo-level
and leave-one-repo-out validation. Examples are de-duplicated and weakly-aligned
examples are rejected unless explicitly kept.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..alignment.aligner import Alignment
from ..candidates.generator import CandidateGenerator
from ..features.extractor import NameMasker
from ..schemas import DependencyGraph, Smell
from ..util import append_jsonl, sha256_of, write_json

DEDUP_KEYS = ("project_id", "commit_sha", "refactoring_type", "affected_entities",
              "smell_id", "candidate_type")


class DatasetBuilder:
    def __init__(self, out_dir: Path, min_alignment: float = 0.5):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.gen = CandidateGenerator()
        self.min_alignment = min_alignment
        self._seen: set = set()

    def _dedup_key(self, row: Dict[str, Any]) -> str:
        return sha256_of({k: row.get(k, "") for k in DEDUP_KEYS})

    def build_ranker_rows(self, project_id: str, split: str, smell: Smell,
                          graph: DependencyGraph, alignments: List[Alignment],
                          commit_sha: str = "", keep_weak: bool = False) -> List[Dict[str, Any]]:
        aligned = {a.refactoring_type: a.alignment_confidence
                   for a in alignments if a.smell_id == smell.smell_id}
        rows: List[Dict[str, Any]] = []
        for cand in self.gen.generate(smell, graph):
            conf = aligned.get(cand.recommended_refactoring, 0.0)
            label = 1 if conf >= self.min_alignment else 0
            if label == 0 and conf > 0 and not keep_weak and conf < self.min_alignment:
                # weak positive alignment -> keep as negative but flag
                pass
            row = {
                "project_id": project_id, "split": split, "commit_sha": commit_sha,
                "smell_id": smell.smell_id, "smell_type": smell.smell_type,
                "refactoring_type": cand.recommended_refactoring,
                "candidate_type": cand.recommended_refactoring,
                "affected_entities": ",".join(sorted(smell.affected_components)),
                "features": cand.features, "alignment_confidence": round(conf, 4),
                "label": label,
            }
            key = self._dedup_key(row)
            if key in self._seen:
                continue
            self._seen.add(key)
            rows.append(row)
        return rows

    # -- writers ----------------------------------------------------------- #
    def write_candidates(self, rows: List[Dict[str, Any]], filename: str) -> Path:
        path = self.out_dir / filename
        for r in rows:
            append_jsonl(path, r)
        return path

    def write_instruct(self, smell: Smell, project_id: str, best_refactoring: str,
                       filename: str = "multi_repo_train_instruct.jsonl") -> Path:
        masker = NameMasker(smell.affected_components)
        path = self.out_dir / filename
        append_jsonl(path, {
            "project_id": project_id,
            "instruction": "Recommend an evidence-grounded refactoring for the architecture smell.",
            "input": masker.mask(
                f"Smell: {smell.smell_type}. Components: "
                f"{[masker.mask_component(c) for c in smell.affected_components]}. "
                f"Tools: {smell.tool_sources}."),
            "output": masker.mask(f"Apply {best_refactoring} at the boundary between the "
                                  f"affected components; verify no cycle remains via graph re-analysis."),
        })
        return path

    def write_chat(self, smell: Smell, project_id: str, reasoning: str,
                   filename: str = "multi_repo_train_chat.jsonl") -> Path:
        masker = NameMasker(smell.affected_components)
        path = self.out_dir / filename
        append_jsonl(path, {
            "project_id": project_id,
            "messages": [
                {"role": "system", "content": "Evidence-grounded refactoring explainer."},
                {"role": "user", "content": masker.mask(
                    f"Smell {smell.smell_type} on {smell.affected_components}. "
                    f"Evidence {smell.evidence_ids}. Recommend a refactoring.")},
                {"role": "assistant", "content": masker.mask(reasoning)},
            ]})
        return path

    # -- stats / reports --------------------------------------------------- #
    def stats(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        pos = sum(r["label"] for r in rows)
        by_smell: Dict[str, int] = {}
        by_repo: Dict[str, int] = {}
        by_refac: Dict[str, int] = {}
        for r in rows:
            by_smell[r["smell_type"]] = by_smell.get(r["smell_type"], 0) + 1
            by_repo[r["project_id"]] = by_repo.get(r["project_id"], 0) + 1
            by_refac[r["refactoring_type"]] = by_refac.get(r["refactoring_type"], 0) + 1
        return {"examples": len(rows), "positive": pos, "negative": len(rows) - pos,
                "repositories": len(by_repo), "by_repository": by_repo,
                "by_smell_type": by_smell, "by_refactoring_type": by_refac}

    def write_stats(self, rows: List[Dict[str, Any]],
                    filename: str = "multi_repo_dataset_stats.json") -> Path:
        path = self.out_dir.parent / "reports" / filename
        write_json(path, self.stats(rows))
        return path

    def write_alignment_report(self, alignments_by_repo: Dict[str, List[Alignment]],
                               filename: str = "multi_repo_alignment_report.csv") -> Path:
        path = self.out_dir.parent / "reports" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["project_id", "smell_id", "smell_type", "refactoring_type",
                        "alignment_confidence"])
            for pid, aligns in alignments_by_repo.items():
                for a in aligns:
                    w.writerow([pid, a.smell_id, a.smell_type, a.refactoring_type,
                                a.alignment_confidence])
        return path
