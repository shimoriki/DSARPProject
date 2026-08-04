"""Repository-level split manager + leakage guard + leave-one-repo-out folds.

Rules enforced:
  - Unseen repos (Cassandra) are NEVER in train/validation/test.
  - A repo used for testing must not appear in training.
  - Splits are by repository, never by shuffling rows within a repo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set

from ..config import load_repo_entries

# substrings that must never leak into training (defence in depth beyond config).
# EXPERIMENT (user 2026-07-29): Cassandra is now a TRAINING repo (too big to test on),
# Log4j2 is the fixed held-out test. The config-driven checks below still forbid any
# test/unseen repo (log4j2, commons-validator) from appearing in the training split.
BLOCKED_IN_TRAINING = ()


class LeakageError(RuntimeError):
    pass


@dataclass
class Fold:
    held_out: str
    train: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return {"held_out": self.held_out, "train": self.train,
                "train_count": len(self.train)}


class SplitManager:
    def __init__(self):
        self.train = [e["project_id"] for e in load_repo_entries("train")]
        self.validation = [e["project_id"] for e in load_repo_entries("validation")]
        self.test = [e["project_id"] for e in load_repo_entries("test")]
        self.unseen = [e["project_id"] for e in load_repo_entries("unseen")]

    # -- guards ------------------------------------------------------------ #
    def assert_no_leakage(self) -> None:
        train_set = set(self.train)
        for blocked in BLOCKED_IN_TRAINING:
            leaked = [p for p in train_set if blocked in p.lower()]
            if leaked:
                raise LeakageError(f"blocked repo(s) in TRAINING: {leaked}")
        # unseen must not appear in train/validation/test
        overlap = set(self.unseen) & (train_set | set(self.validation) | set(self.test))
        if overlap:
            raise LeakageError(f"unseen repo(s) leaked into train/val/test: {sorted(overlap)}")
        # a test repo must not be in training
        t_overlap = set(self.test) & train_set
        if t_overlap:
            raise LeakageError(f"test repo(s) also in training: {sorted(t_overlap)}")

    def is_training_allowed(self, project_id: str) -> bool:
        if any(b in project_id.lower() for b in BLOCKED_IN_TRAINING):
            return False
        # held-out repos (fixed test + random unseen) must never enter training
        return project_id not in self.unseen and project_id not in self.test

    def filter_trainable(self, project_ids: List[str]) -> List[str]:
        return [p for p in project_ids if self.is_training_allowed(p)]

    # -- leave-one-repository-out ----------------------------------------- #
    def loro_folds(self, repos: List[str] | None = None) -> List[Fold]:
        pool = repos if repos is not None else self.train
        pool = self.filter_trainable(pool)
        folds: List[Fold] = []
        for held in pool:
            folds.append(Fold(held_out=held, train=[p for p in pool if p != held]))
        return folds

    def split_of(self, project_id: str) -> str:
        for name, members in (("train", self.train), ("validation", self.validation),
                              ("test", self.test), ("unseen", self.unseen)):
            if project_id in members:
                return name
        return "unknown"

    def summary(self) -> Dict:
        return {"train": self.train, "validation": self.validation,
                "test": self.test, "unseen": self.unseen}
