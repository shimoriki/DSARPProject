import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from dsarp.config import AppConfig  # noqa: E402
from dsarp.store.db import Database  # noqa: E402
from dsarp.store.repos import Store  # noqa: E402


@pytest.fixture()
def cfg(tmp_path: Path) -> AppConfig:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    src = BACKEND.parent / "skills" / "BreakCyclicDependencySkill_v0.md"
    if src.exists():
        (skills_dir / src.name).write_text(src.read_text(encoding="utf-8"),
                                           encoding="utf-8")
    return AppConfig(root_dir=tmp_path, data_dir=Path("data"),
                     db_path=Path("data/test.db"), skills_dir=Path("skills"))


@pytest.fixture()
def store(cfg: AppConfig) -> Store:
    db = Database(cfg.database_path)
    yield Store(db)
    db.close()


@pytest.fixture()
def ctx(cfg, store):
    from dsarp.services import AppContext, ensure_default_skills
    context = AppContext(cfg=cfg, store=store)
    ensure_default_skills(context)
    return context
