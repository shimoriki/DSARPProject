"""Train/validation splitting.

Strategy "by_project_then_instance": when several projects exist, whole
projects are held out first (no leakage across the project boundary);
otherwise smell instances within the project are split deterministically by
seeded hash. A smell instance can never be in both sets — the split is a
single column on evidence_cases.
"""
from __future__ import annotations

import hashlib

from ..config import AppConfig
from ..log import get_logger
from ..store.repos import Store

log = get_logger("splits")


def _bucket(seed: int, key: str) -> float:
    h = hashlib.sha256(f"{seed}:{key}".encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def assign_splits(store: Store, cfg: AppConfig,
                  project_name: str | None = None) -> dict[str, int]:
    frac = cfg.split.validation_fraction
    seed = cfg.split.seed
    projects = store.list_projects()
    if project_name:
        projects = [p for p in projects if p["name"] == project_name]
    if not projects:
        raise ValueError("no projects to split")

    counts = {"train": 0, "validation": 0}

    all_projects = store.list_projects()
    use_project_split = (cfg.split.strategy == "by_project_then_instance"
                         and len(all_projects) > 1 and project_name is None)

    if use_project_split:
        ranked = sorted(all_projects, key=lambda p: _bucket(seed, p["name"]))
        n_val = max(1, round(len(ranked) * frac))
        val_projects = {p["name"] for p in ranked[:n_val]}
        for p in all_projects:
            split = "validation" if p["name"] in val_projects else "train"
            for case in store.list_cases(project_id=p["name"]):
                store.set_case_split(case["id"], split)
                counts[split] += 1
        log.info("project-level split: validation projects = %s", sorted(val_projects))
    else:
        for p in projects:
            for case in store.list_cases(project_id=p["name"]):
                split = "validation" if _bucket(seed, case["id"]) < frac else "train"
                store.set_case_split(case["id"], split)
                counts[split] += 1
        # guarantee at least one validation case when possible
        if counts["validation"] == 0 and counts["train"] > 1:
            case = store.list_cases(project_id=projects[0]["name"])[0]
            store.set_case_split(case["id"], "validation")
            counts["validation"] += 1
            counts["train"] -= 1

    store.audit("split", project_name or "all", "assigned", details=counts)
    return counts
