"""Real package-level moves, mined from history by RefactoringMiner.

The transformer's predictions turned out to carry no signal — 716 log4j2 rows, top-1 label
constant, every confidence inside 0.511-0.521. These do carry signal, because a developer
actually made each one and it survived review.

log4j2's own history holds exactly ONE Move Class, so the pool is drawn across every mined
repository: 102 Move Class + 12 Move And Rename Class. They are used as few-shot examples of
the SHAPE of a real move, never as instructions about the repo being refactored.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Dict, List, Optional

# RefactoringMiner types that correspond to what the Spoon driver can execute.
MOVE_TYPES = ("Move Class", "Move And Rename Class")

# "Move Class a.b.C moved to x.y.C"
_DESC = re.compile(r"Move (?:And Rename )?Class\s+([\w.$]+)\s+moved to\s+([\w.$]+)")


def load(rminer_dir: Path, project_id: Optional[str] = None,
         limit: int = 200) -> List[Dict[str, str]]:
    """Mined moves as {from, to, project}. `project_id` restricts to one repo's history."""
    out: List[Dict[str, str]] = []
    files = ([rminer_dir / f"{project_id}.json"] if project_id
             else sorted(Path(rminer_dir).glob("*.json")))
    for f in files:
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue          # a truncated mining run should not take the pass down
        for commit in data.get("commits", []):
            for ref in commit.get("refactorings") or []:
                if ref.get("type") not in MOVE_TYPES:
                    continue
                m = _DESC.search(ref.get("description", ""))
                if m:
                    out.append({"from": m.group(1), "to": m.group(2), "project": f.stem})
                    if len(out) >= limit:
                        return out
    return out


def as_prompt_block(moves: List[Dict[str, str]], k: int = 6, seed: int = 0) -> str:
    """A few exemplars, deterministically sampled so a rerun sends the same prompt.

    Same-package renames are dropped: they are noise for a model being asked which package a
    type belongs in.
    """
    real = [m for m in moves
            if m["from"].rsplit(".", 1)[0] != m["to"].rsplit(".", 1)[0]]
    if not real:
        return "  (no mined moves available)"
    picked = real if len(real) <= k else random.Random(seed).sample(real, k)
    return "\n".join(f"  {m['from']}  ->  {m['to']}" for m in picked)
