"""Refactoring agents — one per architectural concern, each owning a family of smells.

Every detected smell is routed to exactly one agent, and every agent must return a Plan for
every finding it receives: either an executable refactoring or an explicit, evidence-backed
reason it cannot be automated. Nothing is silently dropped, so
`sum(agent.handled for agent in AGENTS) == total findings` always holds.

    DependencyAgent      Cyclic / Unstable / Hub-Like Dependency
    ModularizationAgent  God Component, Scattered Functionality, Feature Concentration
    EncapsulationAgent   Deficient Encapsulation
    AbstractionAgent     Unutilized / Unnecessary / Multifaceted / Insufficient Modularization
    HierarchyAgent       Missing / Wide / Rebellious / Broken Hierarchy, Broken Modularization

Splitting the policy this way keeps each agent's competence auditable: the dashboard can show
per-agent coverage, and adding a refactoring for a new smell means touching one agent.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .strategies import (Plan, SourceFacts, infer_god_threshold,
                         plan_deficient_encapsulation,
                         plan_extract_interface, plan_god_component,
                         plan_not_automatable, plan_scattered_functionality,
                         plan_unstable_dependency, plan_unutilized_abstraction)
from .hierarchy import plan_introduce_supertype, plan_broken_modularization


@dataclass
class Agent:
    """Owns a set of smell types and turns each finding into a Plan."""
    name: str
    concern: str
    handles: Dict[str, Callable[[SourceFacts, Dict[str, Any]], Plan]]
    handled: int = 0
    plans: List[Plan] = field(default_factory=list)

    def owns(self, smell_type: str) -> bool:
        s = (smell_type or "").lower()
        return any(k in s for k in self.handles)

    def plan(self, facts: SourceFacts, finding: Dict[str, Any]) -> Optional[Plan]:
        s = (finding.get("smell_type") or "").lower()
        for key, planner in self.handles.items():
            if key in s:
                p = planner(facts, finding)
                self.handled += 1
                self.plans.append(p)
                return p
        return None

    def summary(self) -> Dict[str, Any]:
        ok = [p for p in self.plans if p.applicable]
        return {
            "agent": self.name, "concern": self.concern,
            "findings_handled": self.handled,
            "plans_applicable": len(ok),
            "recipe_operations": sum(len(p.entries) for p in ok),
            "smell_types_refactored": sorted({p.smell_type for p in ok}),
            "smell_types_seen": sorted({p.smell_type for p in self.plans}),
            "blocked_reasons": sorted({p.reason for p in self.plans if not p.applicable})[:4],
        }


def build_agents() -> List[Agent]:
    """Fresh agents (they accumulate per-run state, so never share instances)."""
    return [
        Agent("DependencyAgent", "coupling and dependency direction", {
            # cyclic dependency is planned by the loop itself (package merges), so the agent
            # records it as seen without duplicating that work
            "unstable dependency": plan_unstable_dependency,
            "hub-like dependency": plan_god_component,
        }),
        Agent("ModularizationAgent", "package size and cohesion", {
            "god component": plan_god_component,
            "scattered functionality": plan_scattered_functionality,
            "feature concentration": plan_god_component,
        }),
        Agent("EncapsulationAgent", "information hiding", {
            "deficient encapsulation": plan_deficient_encapsulation,
        }),
        Agent("AbstractionAgent", "abstraction quality", {
            "unutilized abstraction": plan_unutilized_abstraction,
            "unnecessary abstraction": plan_unutilized_abstraction,
            "multifaceted abstraction": plan_not_automatable(
                "Multifaceted Abstraction", "Extract Class",
                "the class has several responsibilities; splitting it means inventing a new "
                "type and deciding which fields and methods move with it — that is a design "
                "judgement, and moving members without it would change behaviour"),
            "insufficient modularization": plan_not_automatable(
                "Insufficient Modularization", "Extract Class",
                "the class is too large; shrinking it requires member-level extraction into a "
                "new type, which needs the same design judgement as Multifaceted Abstraction"),
        }),
        Agent("HierarchyAgent", "inheritance and type structure", {
            "missing hierarchy": plan_introduce_supertype,
            "wide hierarchy": plan_introduce_supertype,
            "rebellious hierarchy": plan_extract_interface,
            "broken modularization": plan_broken_modularization,
            "broken hierarchy": plan_not_automatable(
                "Broken Hierarchy", "Replace Inheritance with Delegation",
                "the subtype does not satisfy an IS-A relationship with its supertype; "
                "replacing inheritance with delegation rewrites the public API and every call "
                "site, so it is not safe to apply without review"),
        }),
        Agent("StructureAgent", "system-wide structure", {
            "dense structure": plan_not_automatable(
                "Dense Structure", "Architectural Restructuring",
                "dependency density is a property of the whole system; no single local "
                "refactoring reduces it, so this is reported for architectural review"),
        }),
    ]


def plan_all(repo_path: Path, findings: List[Dict[str, Any]],
             facts: Optional[SourceFacts] = None) -> Dict[str, Any]:
    """Route every finding to its agent. Returns plans plus per-agent coverage."""
    facts = facts or SourceFacts(Path(repo_path))
    # The tool states its own class counts; the smallest package it still flagged bounds the
    # threshold a split has to get under. Computed once and handed to every planner.
    god_threshold = infer_god_threshold(findings)
    agents = build_agents()
    plans: List[Plan] = []
    unrouted: List[str] = []
    seen = set()

    for f in findings:
        smell = f.get("smell_type") or ""
        key = (smell, tuple(f.get("components") or [])[:3])
        if key in seen:
            continue
        seen.add(key)
        if "cyclic" in smell.lower():
            continue                    # owned by the loop's package-merge planner
        f = {**f, "_god_threshold": god_threshold}
        for agent in agents:
            p = agent.plan(facts, f)
            if p is not None:
                if p.applicable and is_expansive(p.smell_type) and not p.resolves_fully:
                    # It would create a package or type the detector flags while leaving the
                    # original smell in place: a guaranteed net loss.
                    p.applicable = False
                    p.reason = ("would create a new package/type the detector flags while "
                                "leaving the original smell in place, so it cannot reduce "
                                "the total; only a fully-resolving split is worth applying")
                plans.append(p)
                break
        else:
            unrouted.append(smell)

    return {
        "plans": plans, "god_threshold": god_threshold,
        "agents": [a.summary() for a in agents if a.handled],
        "unrouted_smell_types": sorted(set(unrouted)),
        "coverage": {
            "smell_types_seen": len({p.smell_type for p in plans}),
            "smell_types_refactored": len({p.smell_type for p in plans if p.applicable}),
            "findings_planned": len(plans),
            "findings_applicable": sum(1 for p in plans if p.applicable),
        },
        "by_smell_type": dict(collections.Counter(
            p.smell_type for p in plans if p.applicable)),
    }


# --------------------------------------------------------------------------- #
# Ranking and budgeting
# --------------------------------------------------------------------------- #

# Some refactorings REMOVE a smell without creating anything new; others necessarily create
# a new package or type that the detector will then flag. Splitting a God Component makes a
# new package that Designite reports as Feature Concentration, so the count goes UP before a
# later pass can consolidate it. Applying both kinds together makes the expansive ones mask
# the clean ones, which is why whole-repo passes looked like "no improvement".
CLEAN_REFACTORINGS = {
    "Deficient Encapsulation",      # field -> private, creates nothing
    "Unutilized Abstraction",       # deletes dead code
    "Unnecessary Abstraction",
    "Unstable Dependency",          # relocates a few classes into an existing package
    "Cyclic Dependency",            # merges a package away, so the graph shrinks
}
EXPANSIVE_REFACTORINGS = {
    "God Component",                # split -> NEW package -> Feature Concentration
    "Feature Concentration",
    "Scattered Functionality",
    "Missing Hierarchy",            # introduces a NEW interface
    "Wide Hierarchy",
    "Rebellious Hierarchy",
}


def rank_plans(plans: List[Plan]) -> List[Plan]:
    """Best-first ordering by what a plan ACHIEVES, not by which smell it targets.

    Every smell type matters equally — a Deficient Encapsulation finding is no less worth
    fixing than a Cyclic Dependency. What separates plans is whether they eliminate the
    finding outright or merely chip at it, so a plan that fully resolves its smell sorts
    first. Ties break on fewer recipe operations: a smaller plan is less likely to interfere
    with another and cheaper to roll back when it does.
    """
    return sorted([p for p in plans if p.applicable],
                  key=lambda p: (0 if p.resolves_fully else 1, len(p.entries), p.smell_type))


def budgeted_plans(plans: List[Plan], budget: int) -> List[Plan]:
    """The `budget` best plans. budget <= 0 means take everything (previous behaviour)."""
    ranked = rank_plans(plans)
    return ranked if budget <= 0 else ranked[:budget]


def is_expansive(smell_type: str) -> bool:
    """True when this refactoring is expected to ADD smells before it removes any."""
    return smell_type in EXPANSIVE_REFACTORINGS
