"""SkillOpt-style optimizer: text-space skill revision, never weight training.

Takes the current skill document plus a feedback digest and asks the local
model for a revised skill. The result is saved as a *_candidate.md file and
registered with status 'candidate'. The production skill file is never
touched; promotion happens only after held-out validation + human approval.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..config import AppConfig
from ..log import get_logger
from ..providers.base import ModelProvider
from ..store.repos import Store

log = get_logger("optimizer")

_SYSTEM = """You are a prompt/skill optimizer for an architectural refactoring agent.
You receive the current skill document (Markdown) and a feedback digest built
from human reviews. Produce an improved version of the skill document.

Requirements for the revision:
- Keep the same overall structure and intent; this is an incremental revision.
- Directly address the weak criteria and repeated complaints in the digest.
- Strengthen evidence-grounding instructions (cite evidence IDs, never invent
  edges or directions, use "Requires source inspection." when facts are missing).
- Keep it concise and actionable; do not add filler.
Return ONLY the full revised Markdown document. No commentary, no code fences."""


def next_version(version: str) -> str:
    m = re.search(r"v(\d+)", version)
    n = int(m.group(1)) + 1 if m else 1
    return f"v{n}"


def optimize_skill(cfg: AppConfig, store: Store, provider: ModelProvider,
                   skill_name: str, skill_version: str, digest: dict) -> dict:
    skill_row = store.get_skill(skill_name, skill_version)
    if not skill_row:
        raise ValueError(f"skill {skill_name} {skill_version} is not registered")
    skill_path = cfg.resolve(skill_row["file_path"])
    current_text = skill_path.read_text(encoding="utf-8")

    user = (
        "BEGIN_SKILLOPT_TASK\n"
        "Current skill document:\nBEGIN_CURRENT_SKILL\n" + current_text +
        "\nEND_CURRENT_SKILL\n\nFeedback digest (aggregated human reviews):\n" +
        json.dumps(digest, indent=2) +
        "\nEND_SKILLOPT_TASK\nReturn the revised skill document now.")

    result = provider.chat(_SYSTEM, user)
    revised = result.text.strip()
    if revised.startswith("```"):
        revised = re.sub(r"^```[a-zA-Z]*\n?", "", revised)
        revised = re.sub(r"\n?```\s*$", "", revised)
    if len(revised) < 200:
        raise ValueError("optimizer returned an implausibly short skill; aborting")

    new_version = next_version(skill_version)
    candidate_name = f"{skill_name}_{new_version}_candidate.md"
    candidate_path = cfg.skills_path / candidate_name
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(revised, encoding="utf-8")

    rel_path = str(Path(cfg.skills_dir) / candidate_name)
    store.register_skill(skill_name, f"{new_version}_candidate", rel_path,
                         status="candidate", parent_version=skill_version,
                         notes=f"generated from digest {digest.get('digest_id', '')}")
    store.audit("skill", f"{skill_name}:{new_version}_candidate", "optimizer_generated",
                details={"base": skill_version, "model": provider.model_id,
                         "tokens": result.total_tokens})
    log.info("candidate skill written: %s", candidate_path)
    return {"skill_name": skill_name, "candidate_version": f"{new_version}_candidate",
            "file_path": rel_path, "base_version": skill_version}
