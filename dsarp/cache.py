"""Hash-based cache. Skips expensive recomputation and duplicate LLM calls.

Cache key = sha256 of (namespace, input-hashes...). Stored as JSON under
data/cache/<namespace>/<key>.json. Cheap, portable, git-ignorable.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from .util import read_json, sha256_of, write_json


class HashCache:
    def __init__(self, root: Path):
        self.root = Path(root) / "cache"

    def key(self, namespace: str, *parts: Any) -> str:
        return sha256_of([namespace, *[str(p) for p in parts]])

    def _path(self, namespace: str, key: str) -> Path:
        return self.root / namespace / f"{key}.json"

    def get(self, namespace: str, key: str) -> Optional[Any]:
        return read_json(self._path(namespace, key), default=None)

    def put(self, namespace: str, key: str, value: Any) -> None:
        write_json(self._path(namespace, key), value)

    def get_or_compute(self, namespace: str, key: str, fn: Callable[[], Any]) -> tuple[Any, bool]:
        """Returns (value, cache_hit)."""
        cached = self.get(namespace, key)
        if cached is not None:
            return cached, True
        value = fn()
        self.put(namespace, key, value)
        return value, False
