"""Plugin registries for smell categories and component types.

New smells or component types are added by calling register_smell_category()
(e.g. from a plugin module) — no schema change required.
"""
from __future__ import annotations

import re

COMPONENT_TYPES = [
    "package",
    "module",
    "class",
    "service",
    "bounded_context",
    "deployment_unit",
]

ARCHITECTURE_TYPES = [
    "package-based-java",
    "modular-monolith",
    "layered",
    "microservices",
    "component-graph",
]

# canonical key -> (display name, short code, synonyms matched case-insensitively)
_SMELL_REGISTRY: dict[str, tuple[str, str, list[str]]] = {}


def register_smell_category(key: str, display: str, code: str, synonyms: list[str]) -> None:
    _SMELL_REGISTRY[key] = (display, code, [s.lower() for s in synonyms])


register_smell_category("cyclic_dependency", "Cyclic Dependency", "CD",
                        ["cyclic dependency", "cyclicdep", "cyclic-dependency", "cycle",
                         "cd", "dependency cycle", "circular dependency", "supercycle"])
register_smell_category("hub_like_dependency", "Hub-Like Dependency", "HL",
                        ["hub-like dependency", "hublikedep", "hublike", "hub like dependency", "hl"])
register_smell_category("unstable_dependency", "Unstable Dependency", "UD",
                        ["unstable dependency", "unstabledep", "unstable-dependency", "ud"])
register_smell_category("god_component", "God Component", "GC",
                        ["god component", "godcomponent", "god class", "insufficient modularization", "gc"])
register_smell_category("layer_violation", "Layer Violation", "LV",
                        ["layer violation", "layering violation", "skip call", "back call", "lv"])
register_smell_category("feature_concentration", "Feature Concentration", "FC",
                        ["feature concentration", "scattered functionality", "fc"])
register_smell_category("microservice_bad_smell", "Microservice Bad Smell", "MS",
                        ["microservice bad smell", "shared persistence", "wrong cuts",
                         "cyclic dependency between services", "ms"])


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def canonical_smell(raw_type: str) -> tuple[str, str, str]:
    """Map a raw tool label to (canonical_key, display_name, short_code).

    Unknown labels become custom_tool_smell — they are kept, never dropped.
    """
    norm = _norm(raw_type)
    compact = norm.replace(" ", "")
    for key, (display, code, synonyms) in _SMELL_REGISTRY.items():
        if norm == key.replace("_", " ") or compact == key.replace("_", ""):
            return key, display, code
        for syn in synonyms:
            if norm == syn or compact == syn.replace(" ", "") or syn in norm:
                return key, display, code
    return "custom_tool_smell", f"Custom Tool Smell ({raw_type})", "XX"


def smell_display(key: str) -> str:
    if key in _SMELL_REGISTRY:
        return _SMELL_REGISTRY[key][0]
    return key


def registered_smells() -> dict[str, str]:
    return {k: v[0] for k, v in _SMELL_REGISTRY.items()}
