"""Closed-loop refactoring-effect verification: apply a suggestion, re-measure smells."""
from .effect_checker import (snapshot_smells, apply_move_class, verify_suggestion,  # noqa: F401
                             simulate_cumulative, SmellSnapshot)
