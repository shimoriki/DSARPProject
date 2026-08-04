"""Training helpers shared by CLI + scripts (kept out of hot import paths).

Ranker training delegates to dsarp.training.RankerTrainer (multi-repo, LORO-capable,
repo-independent features). Outputs land in data/models/.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .config import Config
from .training.ranker_trainer import RankerTrainer


def models_dir(cfg: Config) -> Path:
    return cfg.data_dir / "models"


def train_ranker(cfg: Config, dataset: Optional[Path] = None,
                 validation_repo: Optional[str] = None) -> Path:
    dataset = dataset or (cfg.data_dir / "training" / "candidates.jsonl")
    trainer = RankerTrainer(models_dir(cfg))
    trainer.train(dataset, validation_repo=validation_repo)
    return models_dir(cfg) / "ranker.pkl"
