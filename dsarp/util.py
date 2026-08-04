"""Small shared utilities: hashing, evidence IDs, JSON IO, token estimation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


def sha256_of(obj: Any) -> str:
    """Stable content hash of any JSON-serialisable object (or raw bytes/str)."""
    if isinstance(obj, (bytes, bytearray)):
        return hashlib.sha256(obj).hexdigest()
    if isinstance(obj, str):
        return hashlib.sha256(obj.encode("utf-8")).hexdigest()
    payload = json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def evidence_id(prefix: str, *parts: Any) -> str:
    """Deterministic short evidence ID, e.g. EVID_ab12cd34."""
    digest = sha256_of([str(p) for p in parts])[:8]
    return f"{prefix}_{digest}"


def estimate_tokens(text: str) -> int:
    """Cheap heuristic token estimate (~4 chars/token) — no tokenizer dep."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def read_json(path: Path, default: Any = None) -> Any:
    if not Path(path).exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        # corrupt/truncated file (e.g. a tool run killed mid-write) -> treat as absent
        return default


def write_json(path: Path, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, default=str, ensure_ascii=False)


def append_jsonl(path: Path, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, default=str, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> Iterable[dict]:
    if not Path(path).exists():
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)
