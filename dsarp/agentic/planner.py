"""The LLM planner: catalogue operations, checked against the graph and simulated before any code moves.

The model only proposes. Names are checked against the baseline class graph, each move against the
same rules the beam planner obeys, and the kept operations are simulated on the package graph.
Rejections and what still cycles go back to the model as feedback, for at most `rounds` rounds.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ..refactoring.scc_planner import _pkg, components, package_edges, top_level_edges
from .context import build_context, render

Op = Tuple[str, str, str]


def _first_json(text: str) -> Optional[Dict[str, Any]]:
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def parse_ops(text: str) -> Tuple[List[Op], List[str]]:
    obj = _first_json(text or "")
    if obj is None:
        return [], ["no JSON object in the answer"]
    ops: List[Op] = []
    errs: List[str] = []
    for o in obj.get("operations") or []:
        if not isinstance(o, dict):
            errs.append("operation is not an object: %r" % (o,))
        elif o.get("op") == "moveClass" and o.get("class") and o.get("to"):
            ops.append(("move", str(o["class"]), str(o["to"])))
        elif o.get("op") == "invertEdge" and o.get("consumer") and o.get("impl"):
            ops.append(("invert", str(o["consumer"]), str(o["impl"])))
        else:
            errs.append("not in the catalogue: %s" % json.dumps(o)[:120])
    return ops, errs


def _label(op: Op) -> str:
    return "moveClass %s" % op[1] if op[0] == "move" else "invertEdge %s %s" % (op[1], op[2])


def validate(ops: List[Op], edges, comp: Set[str], accept: Callable[[str, str], bool],
             blocked: Optional[Callable[[str, str, Dict[str, str]], Optional[str]]]) -> Dict[str, Any]:
    tl = top_level_edges(edges)
    classes = {c for e in tl for c in e}
    packages = {_pkg(c) for c in classes}
    kept: List[Op] = []
    rejected: List[List[str]] = []
    moved: Dict[str, str] = {}
    for op in ops:
        kind, a, b = op
        if kind == "move":
            why = ("unknown class" if a not in classes else
                   "unknown package" if b not in packages else
                   # The beam planner only moves into the cycle's own packages; same space here.
                   "destination outside the cycle" if b not in comp else
                   "class moved twice" if a in moved else
                   "refused: move rule" if not accept(a, b) else None)
            if not why:
                moved[a] = b
        else:
            why = ("unknown class" if b not in classes else
                   "unknown package" if a not in packages else
                   "inversions are off" if blocked is None else
                   blocked(a, b, moved))
        if why:
            rejected.append([_label(op), why])
        else:
            kept.append(op)
    inv = [(a, b) for k, a, b in kept if k == "invert"]
    base = set().union(*components(package_edges(tl, {})))
    now = components(package_edges(tl, moved, inv))
    cycling = set().union(*now) if now else set()
    left = cycling & comp
    return {"ops": kept, "rejected": rejected, "predicted_left": len(left),
            "pulled_in": len(cycling - base), "left_packages": sorted(left)}


def llm_plan(model, edges, comp: Set[str], accept: Callable[[str, str], bool],
             blocked, rounds: int = 3) -> Dict[str, Any]:
    ctx = build_context(edges, comp)
    plan: Dict[str, Any] = {"component": sorted(comp), "size": len(comp), "moves": [],
                            "inversions": [], "predicted_left": len(comp), "dissolves": False,
                            "planner": "llm", "rounds": []}
    feedback, best = "", None
    for _ in range(rounds):
        try:
            done = model.generate(render(ctx, feedback), max_tokens=800, temperature=0.2, json_mode=True)
        except Exception as e:                       # endpoint down, timeout, bad response shape
            plan["why"] = "model call failed: %s" % str(e)[:200]
            break
        ops, errs = parse_ops(done.text)
        v = validate(ops, edges, comp, accept, blocked)
        plan["rounds"].append({"text": done.text[:2000], "parse_errors": errs, "rejected": v["rejected"],
                               "kept": [list(o) for o in v["ops"]], "predicted_left": v["predicted_left"],
                               "pulled_in": v["pulled_in"], "prompt_tokens": done.prompt_tokens,
                               "completion_tokens": done.completion_tokens})
        key = (v["pulled_in"] > 0, v["predicted_left"], len(v["ops"]))
        if best is None or key < best[0]:
            best = (key, v)
        if not v["rejected"] and not errs and v["pulled_in"] == 0 and v["predicted_left"] == 0:
            break
        feedback = "\n".join(["%s: %s" % (lbl, why) for lbl, why in v["rejected"]] + errs
                             + ["still cycling: %s" % ", ".join(v["left_packages"]) if v["left_packages"]
                                else "nothing left cycling", ]
                             + (["pulls %d outside package(s) into a cycle" % v["pulled_in"]]
                                if v["pulled_in"] else []))
    if best is not None and not best[0][0]:
        v = best[1]
        plan.update(moves=sorted([a, b] for k, a, b in v["ops"] if k == "move"),
                    inversions=sorted([a, b] for k, a, b in v["ops"] if k == "invert"),
                    predicted_left=v["predicted_left"], dissolves=v["predicted_left"] == 0)
    return plan
