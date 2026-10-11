"""Per-suggestion accounting: what each recommendation covered, and how far it got.

A single "accuracy" number cannot describe this pipeline, because a recommendation can fail at
five different places and each failure means something different. A label with no parameters is
not the same failure as a change that broke the build, which is not the same as a change that
built and made the architecture worse. So the funnel is reported stage by stage.

    sampled                 rows in the model's suggestion CSV
    concrete                the generator turned it into a real source change with parameters
    attempted               it survived screening and was actually applied in a batch
    mechanically ok         the resulting tree built to the same module set as its baseline
    comparable              Arcan ran on that tree, so its count means something
    target improved         the SPECIFIC smell the suggestion named disappeared
    regression free         ... and the overall count did not rise

The target-smell test is the part that needs care. A suggestion names a smell and the elements it
affects; for a cyclic dependency those elements are the packages in the cycle. The suggestion
succeeded on its own terms only if a cycle over those packages is gone afterwards, which is a
different question from whether the total fell. A batch can cut the total while leaving every
targeted cycle intact, and one did.

Attribution granularity is stated per row and never hidden: a suggestion applied in a batch of
one is attributed exactly, while one applied alongside eleven others shares its batch's outcome.
Both are reported; the rates are given for the exactly-attributed subset as well as for all.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .arcan_diff import cycle_sets, hubs, unstable_pairs

STATUS_ORDER = ["sampled", "concrete", "attempted", "mechanical_ok", "comparable",
                "target_improved", "regression_free"]


def load_suggestions(csv_path: Path) -> List[Dict[str, str]]:
    csv.field_size_limit(10 ** 9)
    with Path(csv_path).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_manifest(path: Path) -> List[Dict[str, Any]]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return doc if isinstance(doc, list) else doc.get("records", [])


def targeted_key(affected: List[str]) -> frozenset:
    """The identity of the smell a suggestion names: the set of elements it lists."""
    return frozenset(a.strip() for a in affected if a and a.strip())


def smell_present(arcan_dir: Path, smell: str, key: frozenset) -> bool:
    """Is a smell matching this suggestion's elements present in that Arcan run?

    A cyclic dependency matches when a cycle's member set INTERSECTS the named elements in two
    or more places: the suggestion lists the packages it believes are tangled, and Arcan's own
    cycle may be a subset or a superset of that list.
    """
    s = (smell or "").lower()
    if "cyc" in s:
        for level in ("package", "class"):
            for members in cycle_sets(arcan_dir, level):
                if len(members & key) >= 2:
                    return True
        return False
    if "unstable" in s:
        return any(a in key or b in key for a, b in unstable_pairs(arcan_dir))
    if "hub" in s:
        return any(h in key for h in hubs(arcan_dir))
    return False


def build_ledger(repo: str, suggestions_csv: Path, manifest: Path, before_arcan: Path,
                 batch_roots: Dict[str, Path]) -> List[Dict[str, Any]]:
    """One row per model recommendation, carrying how far it got and why it stopped."""
    rows = load_suggestions(suggestions_csv)
    records = load_manifest(manifest)
    by_id = {str(r.get("prediction_id")): r for r in records}

    # which batch each moved type landed in, per arm, with that batch's outcome
    placement: Dict[str, Dict[str, Any]] = {}
    for arm, root in batch_roots.items():
        res_file = Path(root) / "results.json"
        if not res_file.exists():
            continue
        for i, b in enumerate(json.loads(res_file.read_text(encoding="utf-8")), 1):
            after = Path(root) / ("batch%d" % i) / "measure" / "arcan"
            for t in (b.get("types") or []):
                placement.setdefault(t, {
                    "arm": arm, "label": b.get("label"), "batch_size": b.get("moves"),
                    "apply_status": b.get("apply_status"), "build": b.get("build") or {},
                    "verdict": b.get("verdict") or {}, "after_arcan": after,
                })

    ledger = []
    for idx, row in enumerate(rows, 1):
        rec = by_id.get(str(idx))
        affected = [a.strip() for a in (row.get("affected_elements") or "").split("|") if a.strip()]
        key = targeted_key(affected)
        entry: Dict[str, Any] = {
            "repo": repo, "id": idx,
            "smell": row.get("architecture_smell"),
            "elements": affected,
            "element_count": len(affected),
            "top_suggestion": (row.get("suggestions") or "").split("|")[0].split("(")[0].strip(),
            "stage": "sampled", "why": "", "attribution": "",
        }
        if not rec or rec.get("status") != "ready_for_dry_run":
            entry["why"] = (rec or {}).get("reason") or "no concrete candidate produced"
            entry["concrete_status"] = (rec or {}).get("status", "missing")
            ledger.append(entry)
            continue

        entry.update(stage="concrete", concrete_status="ready_for_dry_run",
                     moves=rec.get("source_type"), destination=rec.get("destination_type"),
                     risk=rec.get("risk_level"))
        place = placement.get(rec.get("source_type"))
        if not place:
            entry["why"] = "screened out as unable to compile elsewhere, or never batched"
            ledger.append(entry)
            continue

        entry.update(stage="attempted", arm=place["arm"], batch=place["label"],
                     batch_size=place["batch_size"],
                     attribution="exact" if place["batch_size"] == 1 else "shared")
        b, v = place["build"], place["verdict"]
        if place["apply_status"] != "changed":
            entry["why"] = "apply did not complete: %s" % place["apply_status"]
            ledger.append(entry)
            continue
        if not v.get("comparable"):
            entry["stage"] = "mechanical_ok" if (b.get("modules_failure") == 0) else "attempted"
            entry["why"] = v.get("why") or "not comparable"
            ledger.append(entry)
            continue

        entry.update(stage="comparable", delta=v.get("delta"),
                     before=v.get("before"), after=v.get("after"))
        was = smell_present(before_arcan, entry["smell"], key)
        now = smell_present(place["after_arcan"], entry["smell"], key)
        entry["target_present_before"] = was
        entry["target_present_after"] = now
        if was and not now:
            entry["stage"] = "target_improved"
            if (v.get("delta") or 0) <= 0:
                entry["stage"] = "regression_free"
            else:
                entry["why"] = "target smell gone but the total rose by %+d" % v["delta"]
        elif not was:
            entry["why"] = "the named smell was not present in the baseline under this identity"
        else:
            entry["why"] = "target smell still present after the change"
        ledger.append(entry)
    return ledger


def funnel(ledger: List[Dict[str, Any]], only_exact: bool = False) -> Dict[str, Any]:
    rows = [r for r in ledger
            if not only_exact or r.get("attribution") in ("exact", "")] if only_exact else ledger
    if only_exact:
        rows = [r for r in ledger if r.get("attribution") != "shared"]
    reached = {s: 0 for s in STATUS_ORDER}
    for r in rows:
        hit = STATUS_ORDER.index(r["stage"])
        for i in range(hit + 1):
            reached[STATUS_ORDER[i]] += 1

    def rate(a: str, b: str) -> Optional[float]:
        return round(100.0 * reached[a] / reached[b], 1) if reached[b] else None

    return {"counts": reached, "n": len(rows), "rates": {
        "resolution": rate("concrete", "sampled"),
        "mechanical_success": rate("comparable", "attempted"),
        "target_smell_improvement": rate("target_improved", "comparable"),
        "regression_free_improvement": rate("regression_free", "comparable"),
        "end_to_end": rate("regression_free", "sampled")}}
