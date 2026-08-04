"""Config system — layered YAML profiles (local/hpc) + repo lists.

Loads configs/*.yaml. Falls back to sane defaults so the pipeline runs with
zero config on a laptop. Profiles select providers, storage, and budgets.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIGS_DIR = REPO_ROOT / "configs"
DATA_DIR = REPO_ROOT / "data"


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists() or yaml is None:
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@dataclass
class Config:
    profile: str = "local"
    raw: Dict[str, Any] = field(default_factory=dict)
    data_dir: Path = DATA_DIR

    # --- convenience accessors -------------------------------------------- #
    @property
    def db_path(self) -> Path:
        return self.data_dir / self.raw.get("db_path", "dsarp.sqlite")

    @property
    def token_budget(self) -> Dict[str, int]:
        return self.raw.get("token_budget", {
            "max_input_tokens": 6000,
            "max_output_tokens": 1200,
            "reserved_output_tokens": 1200,
        })

    @property
    def model_provider(self) -> Dict[str, Any]:
        return self.raw.get("model_provider", {
            "type": "offline",          # offline | ollama | llamacpp | openai | vllm
            "model": "qwen2.5-coder:7b",
            "base_url": "http://localhost:11434",
        })

    @property
    def quality_gate(self) -> Dict[str, Any]:
        """Only emit valid, high-accuracy suggestions. `requires_source_inspection`
        (honest uncertainty) does NOT fail the gate; unsupported claims do."""
        return self.raw.get("quality_gate", {
            "min_confidence": 0.30, "require_valid": True, "require_evidence": True,
        })

    @property
    def tools_config(self) -> Dict[str, Any]:
        return self.raw.get("tools", {})

    @property
    def refactoringminer_config(self) -> Dict[str, Any]:
        return self.raw.get("refactoringminer", {
            "mode": "import", "executable_path": "",
            "output_dir": "data/raw/refactoringminer",
        })

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    def memory_dir(self, project_id: str) -> Path:
        return self.data_dir / "memory" / project_id


def load_config(profile: str = "local", overrides: Dict[str, Any] | None = None) -> Config:
    """Load configs/<profile>.yaml with env + override merge."""
    profile = os.environ.get("DSARP_PROFILE", profile)
    raw = _load_yaml(CONFIGS_DIR / f"{profile}.yaml")
    if overrides:
        raw.update(overrides)
    data_dir = Path(raw.get("data_dir", DATA_DIR))
    return Config(profile=profile, raw=raw, data_dir=data_dir)


def _slug_to_project_id(slug: str) -> str:
    return slug.replace("/", "-")


def load_repo_entries(kind: str) -> List[Dict[str, str]]:
    """kind ∈ {train, validation, test, unseen}. Returns [{project_id, repo_url, split}].

    Accepts both the rich dict format and plain "org/name" strings (back-compat).
    """
    data = _load_yaml(CONFIGS_DIR / f"repos_{kind}.yaml")
    split = data.get("split", kind)
    out: List[Dict[str, str]] = []
    for entry in data.get("repositories", []):
        if isinstance(entry, str):
            out.append({"project_id": _slug_to_project_id(entry),
                        "repo_url": f"https://github.com/{entry}", "split": split})
        elif isinstance(entry, dict):
            pid = entry.get("project_id") or _slug_to_project_id(entry.get("repo_url", "").split("github.com/")[-1])
            out.append({"project_id": pid, "repo_url": entry.get("repo_url", ""), "split": split})
    return out


def load_repo_list(kind: str) -> List[str]:
    """Back-compat: returns project_ids for a split kind."""
    return [e["project_id"] for e in load_repo_entries(kind)]


def all_splits() -> Dict[str, List[Dict[str, str]]]:
    return {k: load_repo_entries(k) for k in ("train", "validation", "test", "unseen")}
