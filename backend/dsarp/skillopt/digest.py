"""Feedback digest: aggregate completed human reviews for one skill version."""
from __future__ import annotations

import json
import re
from collections import Counter

from ..hgrs import CRITERIA
from ..log import get_logger
from ..store.repos import Store

log = get_logger("digest")

_STOPWORDS = set("""a an and are as at be but by for from has have if in into is it its of on or
that the this to was were will with would should could very too not no than then when
i you he she they we them my your there here what which who whom about""".split())


def _complaint_terms(notes: list[str], top_n: int = 12) -> list[tuple[str, int]]:
    counter: Counter = Counter()
    for note in notes:
        words = re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", note.lower())
        counter.update(w for w in words if w not in _STOPWORDS)
    return counter.most_common(top_n)


def build_digest(store: Store, skill_name: str, skill_version: str) -> dict:
    rows = store.reviews_for_skill(skill_name, skill_version)
    if not rows:
        raise ValueError(
            f"no completed reviews found for skill {skill_name} {skill_version}; "
            "review some agent runs first")

    n = len(rows)
    mean_hgrs = round(sum(r["hgrs"] for r in rows) / n, 3)
    by_criterion = {c: round(sum(r[c] for r in rows) / n, 2) for c in CRITERIA}
    weak_criteria = sorted((c for c in CRITERIA if by_criterion[c] < 3.5),
                           key=lambda c: by_criterion[c])

    lowest = sorted(rows, key=lambda r: r["hgrs"])[:3]
    lowest_outputs = []
    for r in lowest:
        note = (r.get("reviewer_notes") or "").strip()
        lowest_outputs.append({
            "run_id": r["run_id"], "hgrs": r["hgrs"],
            "reviewer_notes": note[:600],
            "decision": r.get("decision"),
        })

    unsupported_claims = 0
    missing_steps = 0
    risk_omissions = 0
    tokens, runtimes = [], []
    for r in rows:
        sc = json.loads(r["structural_checks_json"] or "{}")
        if sc.get("critical_hallucination"):
            unsupported_claims += 1
        for check in sc.get("checks", []):
            if check["name"] == "at_least_three_concrete_steps" and not check["passed"]:
                missing_steps += 1
            if check["name"] == "risks_and_tradeoffs_present" and not check["passed"]:
                risk_omissions += 1
        if r.get("total_tokens"):
            tokens.append(r["total_tokens"])
        if r.get("runtime_seconds"):
            runtimes.append(r["runtime_seconds"])

    notes = [r.get("reviewer_notes") or "" for r in rows if r.get("reviewer_notes")]
    digest = {
        "skill_name": skill_name,
        "skill_version": skill_version,
        "reviews_aggregated": n,
        "mean_hgrs": mean_hgrs,
        "mean_by_criterion": by_criterion,
        "weak_criteria": weak_criteria,
        "lowest_rated_outputs": lowest_outputs,
        "common_reviewer_complaints": _complaint_terms(notes),
        "reviewer_notes_sample": [n_[:400] for n_ in notes[:10]],
        "unsupported_evidence_claim_rate": round(unsupported_claims / n, 3),
        "missing_steps_rate": round(missing_steps / n, 3),
        "risk_omission_rate": round(risk_omissions / n, 3),
        "mean_total_tokens": round(sum(tokens) / len(tokens), 1) if tokens else None,
        "mean_runtime_seconds": round(sum(runtimes) / len(runtimes), 2) if runtimes else None,
        "would_try_yes_pct": round(
            100 * sum(1 for r in rows if r["would_try_it"] == "yes") / n, 1),
    }
    digest_id = store.save_digest(skill_name, skill_version, digest)
    digest["digest_id"] = digest_id
    log.info("digest for %s %s: mean HGRS %.3f over %d reviews",
             skill_name, skill_version, mean_hgrs, n)
    return digest
