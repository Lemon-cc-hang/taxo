"""Cost tracking and enforcement for LLM API calls.

Tracks cumulative API spend per month in a JSONL file, enforces per-call
and monthly budget limits based on conservative pricing estimates.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

from taxo.config import CostConfig

logger = logging.getLogger(__name__)

# Conservative pricing: over-estimate slightly so we never silently exceed budget.
# DeepSeek-chat: $0.14/M input, $0.28/M output.  We round up.
INPUT_COST_PER_M = 0.15   # USD per million input tokens
OUTPUT_COST_PER_M = 0.30  # USD per million output tokens

# When estimating before a call, assume a 3:1 output:input ratio as worst case.
DEFAULT_OUTPUT_RATIO = 3.0


class BudgetExceededError(Exception):
    """Raised when a call would exceed the configured budget and action is 'block'."""


class CostTracker:
    """Tracks cumulative LLM API costs per month."""

    def __init__(self, config: CostConfig, cost_file: Path | None = None) -> None:
        self._config = config
        self._cost_file = cost_file or (Path.home() / ".taxo" / "cost.jsonl")

    # -- pre-call guard -------------------------------------------------------

    def check_before_call(self, estimated_input_tokens: int) -> bool:
        """Return True if the call is within budget, False if blocked.

        For ``over_budget_action == "warn"`` this always returns True after
        logging a warning.  For ``"block"`` it returns False when either the
        per-call cap or the monthly budget would be exceeded.
        """
        # Estimate cost conservatively: assume output tokens are 3x input.
        estimated_output = int(estimated_input_tokens * DEFAULT_OUTPUT_RATIO)
        estimated_cost = self._estimate_cost(estimated_input_tokens, estimated_output)

        # Per-call cap
        if estimated_cost > self._config.max_cost_per_call:
            msg = (
                f"Estimated cost ${estimated_cost:.6f} exceeds per-call limit "
                f"${self._config.max_cost_per_call:.6f}"
            )
            if self._config.over_budget_action == "block":
                logger.warning(f"BLOCKED: {msg}")
                return False
            else:
                logger.warning(f"WARN: {msg}")

        # Monthly budget
        monthly_spend = self.get_monthly_spend()
        if monthly_spend + estimated_cost > self._config.monthly_budget:
            msg = (
                f"Monthly spend ${monthly_spend + estimated_cost:.4f} would exceed "
                f"budget ${self._config.monthly_budget:.2f}"
            )
            if self._config.over_budget_action == "block":
                logger.warning(f"BLOCKED: {msg}")
                return False
            else:
                logger.warning(f"WARN: {msg}")

        return True

    # -- post-call recording --------------------------------------------------

    def record_usage(self, input_tokens: int, output_tokens: int) -> float:
        """Record actual token usage and return the calculated cost."""
        cost = self._estimate_cost(input_tokens, output_tokens)
        entry = {
            "date": date.today().isoformat(),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
        }
        self._cost_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._cost_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
        logger.debug(
            f"Recorded usage: {input_tokens} in + {output_tokens} out = ${cost:.6f}"
        )
        return cost

    # -- queries --------------------------------------------------------------

    def get_monthly_spend(self) -> float:
        """Total spend for the current calendar month."""
        today = date.today()
        year, month = today.year, today.month
        total = 0.0
        if not self._cost_file.exists():
            return total
        for line in self._cost_file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entry_date = datetime.strptime(entry["date"], "%Y-%m-%d").date()
                if entry_date.year == year and entry_date.month == month:
                    total += entry.get("cost", 0.0)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        return total

    def get_stats(self) -> dict:
        """Return a dict of cost statistics for display."""
        today = date.today()
        year, month = today.year, today.month
        total_cost = 0.0
        total_calls = 0
        total_input = 0
        total_output = 0

        if self._cost_file.exists():
            for line in self._cost_file.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entry_date = datetime.strptime(entry["date"], "%Y-%m-%d").date()
                    if entry_date.year == year and entry_date.month == month:
                        total_cost += entry.get("cost", 0.0)
                        total_calls += 1
                        total_input += entry.get("input_tokens", 0)
                        total_output += entry.get("output_tokens", 0)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

        return {
            "monthly_spend": round(total_cost, 6),
            "monthly_budget": self._config.monthly_budget,
            "budget_remaining": round(self._config.monthly_budget - total_cost, 6),
            "total_calls": total_calls,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "max_cost_per_call": self._config.max_cost_per_call,
            "over_budget_action": self._config.over_budget_action,
        }

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * INPUT_COST_PER_M / 1_000_000) + (
            output_tokens * OUTPUT_COST_PER_M / 1_000_000
        )
