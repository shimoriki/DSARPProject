"""Token budget manager + per-call usage log (token optimisation layer).

Enforces: count before every model call, reject over-budget prompts, log usage.
Compaction hooks let callers shrink context before re-trying.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .schemas import TokenBudget
from .util import append_jsonl, estimate_tokens


class TokenBudgetError(RuntimeError):
    pass


@dataclass
class UsageRecord:
    task_type: str
    model_id: str
    input_token_estimate: int
    output_token_estimate: int
    actual_prompt_tokens: Optional[int] = None
    actual_completion_tokens: Optional[int] = None
    cache_hit: bool = False
    context_package_id: str = ""
    evidence_ids_used: List[str] = field(default_factory=list)


class TokenBudgetManager:
    def __init__(self, budget: TokenBudget, log_path: Optional[Path] = None):
        self.budget = budget
        self.log_path = Path(log_path) if log_path else None
        self.records: List[UsageRecord] = []

    # -- pre-flight -------------------------------------------------------- #
    def check_prompt(self, prompt: str) -> int:
        """Return estimated input tokens; raise if over budget."""
        est = estimate_tokens(prompt)
        if est > self.budget.max_input_tokens:
            raise TokenBudgetError(
                f"prompt {est} tok exceeds max_input_tokens {self.budget.max_input_tokens}"
            )
        return est

    def fits(self, prompt: str) -> bool:
        return estimate_tokens(prompt) <= self.budget.max_input_tokens

    # -- logging ----------------------------------------------------------- #
    def log(self, record: UsageRecord) -> None:
        self.records.append(record)
        if self.log_path:
            append_jsonl(self.log_path, record.__dict__)

    # -- reporting --------------------------------------------------------- #
    def summary(self) -> dict:
        hits = sum(1 for r in self.records if r.cache_hit)
        return {
            "total_model_calls": len(self.records),
            "cache_hits": hits,
            "cache_misses": len(self.records) - hits,
            "estimated_input_tokens": sum(r.input_token_estimate for r in self.records),
            "estimated_output_tokens": sum(r.output_token_estimate for r in self.records),
            "actual_prompt_tokens": sum((r.actual_prompt_tokens or 0) for r in self.records),
            "actual_completion_tokens": sum((r.actual_completion_tokens or 0) for r in self.records),
        }
