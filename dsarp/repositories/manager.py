"""Loop 1 — repository acquisition. Clone/update Java repos, list commits.

Uses git via subprocess when available; degrades gracefully (records status)
so the pipeline stays runnable offline. Never reads whole repos (token policy).
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


def slug_to_dirname(slug: str) -> str:
    return slug.replace("/", "-")


@dataclass
class RepoStatus:
    slug: str
    path: str
    exists: bool
    branch: Optional[str] = None
    head: Optional[str] = None
    commit_count: Optional[int] = None
    note: str = ""


class RepositoryManager:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.root = Path(data_dir) / "raw" / "repos"
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.data_dir / "repos_registry.json"

    def _registry(self) -> dict:
        import json
        if self.registry_path.exists():
            return json.loads(self.registry_path.read_text(encoding="utf-8"))
        return {}

    def register_local(self, project_id: str, path: str) -> None:
        import json
        reg = self._registry()
        reg[project_id] = {"local_path": str(Path(path).resolve())}
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(json.dumps(reg, indent=2), encoding="utf-8")

    def path_for(self, slug: str) -> Path:
        reg = self._registry()
        if slug in reg and reg[slug].get("local_path"):
            return Path(reg[slug]["local_path"])
        return self.root / slug_to_dirname(slug)

    def _git(self, *args: str, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=600,
        )

    @staticmethod
    def _has_git() -> bool:
        return shutil.which("git") is not None

    def clone(self, slug: str, url: Optional[str] = None, depth: Optional[int] = None) -> RepoStatus:
        dest = self.path_for(slug)
        if not self._has_git():
            dest.mkdir(parents=True, exist_ok=True)
            return RepoStatus(slug, str(dest), exists=dest.exists(),
                              note="git not installed; created placeholder dir")
        url = url or f"https://github.com/{slug}.git"
        if (dest / ".git").exists():
            self._git("fetch", "--all", cwd=dest)
        else:
            args = ["clone", url, str(dest)]
            if depth:
                args = ["clone", "--depth", str(depth), url, str(dest)]
            res = self._git(*args)
            if res.returncode != 0:
                return RepoStatus(slug, str(dest), exists=False,
                                  note=f"clone failed: {res.stderr.strip()[:200]}")
        return self.status(slug)

    def status(self, slug: str) -> RepoStatus:
        dest = self.path_for(slug)
        if not (dest / ".git").exists():
            return RepoStatus(slug, str(dest), exists=dest.exists(), note="not a git repo")
        branch = self._git("rev-parse", "--abbrev-ref", "HEAD", cwd=dest).stdout.strip()
        head = self._git("rev-parse", "HEAD", cwd=dest).stdout.strip()
        count = self._git("rev-list", "--count", "HEAD", cwd=dest).stdout.strip()
        return RepoStatus(slug, str(dest), True, branch=branch, head=head,
                          commit_count=int(count) if count.isdigit() else None)

    def list_commits(self, slug: str, limit: int = 50) -> List[str]:
        dest = self.path_for(slug)
        if not (dest / ".git").exists():
            return []
        out = self._git("log", f"-{limit}", "--pretty=%H", cwd=dest).stdout
        return [ln.strip() for ln in out.splitlines() if ln.strip()]

    def checkout(self, slug: str, revision: str) -> bool:
        dest = self.path_for(slug)
        if not (dest / ".git").exists():
            return False
        return self._git("checkout", revision, cwd=dest).returncode == 0
