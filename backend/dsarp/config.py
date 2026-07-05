"""Configuration: YAML file + environment overrides (env wins)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

from .hgrs import DEFAULT_WEIGHTS, validate_weights


class ModelConfig(BaseModel):
    provider: str = "mock"  # ollama | openai_compat | llamacpp | hf_endpoint | mock
    base_url: str = "http://localhost:11434"
    model_id: str = "mock"
    temperature: float = 0.2
    max_tokens: int = 1400
    timeout_seconds: int = 300
    api_key: str = ""


class CriticConfig(BaseModel):
    enabled: bool = False
    provider: Optional[str] = None
    model_id: Optional[str] = None


class SplitConfig(BaseModel):
    strategy: str = "by_project_then_instance"
    validation_fraction: float = 0.3
    seed: int = 13


class PromotionConfig(BaseModel):
    min_hgrs_improvement: float = 0.10
    max_grounding_drop: float = 0.0


class AppConfig(BaseModel):
    root_dir: Path = Field(default_factory=Path.cwd)
    data_dir: Path = Path("data")
    db_path: Path = Path("data/dsarp.db")
    skills_dir: Path = Path("skills")
    reviewer_id: str = "local_user"
    model: ModelConfig = Field(default_factory=ModelConfig)
    critic: CriticConfig = Field(default_factory=CriticConfig)
    tools: dict[str, dict[str, Any]] = Field(default_factory=dict)
    hgrs_weights: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    split: SplitConfig = Field(default_factory=SplitConfig)
    promotion: PromotionConfig = Field(default_factory=PromotionConfig)
    allow_source_inspection: bool = True

    def resolve(self, p: Path | str) -> Path:
        p = Path(p)
        return p if p.is_absolute() else (self.root_dir / p)

    @property
    def database_path(self) -> Path:
        return self.resolve(self.db_path)

    @property
    def skills_path(self) -> Path:
        return self.resolve(self.skills_dir)

    @property
    def data_path(self) -> Path:
        return self.resolve(self.data_dir)


def _env(name: str) -> Optional[str]:
    v = os.environ.get(name)
    return v if v not in (None, "") else None


def load_config(config_path: str | Path | None = None, root_dir: str | Path | None = None) -> AppConfig:
    """Load config.yaml (if present) and apply DSARP_* environment overrides."""
    root = Path(root_dir) if root_dir else Path.cwd()
    path = config_path or _env("DSARP_CONFIG")
    candidates = [Path(path)] if path else [root / "config" / "config.yaml",
                                            root / "config" / "config.example.yaml"]
    raw: dict[str, Any] = {}
    for cand in candidates:
        cand = cand if cand.is_absolute() else root / cand
        if cand.exists():
            raw = yaml.safe_load(cand.read_text(encoding="utf-8")) or {}
            break

    cfg = AppConfig(root_dir=root, **raw)

    if v := _env("DSARP_DB_PATH"):
        cfg.db_path = Path(v)
    if v := _env("DSARP_REVIEWER_ID"):
        cfg.reviewer_id = v
    if v := _env("DSARP_MODEL_PROVIDER"):
        cfg.model.provider = v
    if v := _env("DSARP_MODEL_BASE_URL"):
        cfg.model.base_url = v
    if v := _env("DSARP_MODEL_ID"):
        cfg.model.model_id = v
    if v := _env("DSARP_MODEL_TEMPERATURE"):
        cfg.model.temperature = float(v)
    if v := _env("DSARP_MODEL_MAX_TOKENS"):
        cfg.model.max_tokens = int(v)
    if v := _env("DSARP_API_KEY"):
        cfg.model.api_key = v

    validate_weights(cfg.hgrs_weights)
    return cfg
