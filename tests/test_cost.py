"""Tests for CostTracker: budget checks, recording, monthly aggregation, block vs warn."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from taxo.config import CostConfig
from taxo.cost import CostTracker


@pytest.fixture
def cost_file(tmp_path: Path) -> Path:
    return tmp_path / "cost.jsonl"


@pytest.fixture
def tracker(cost_file: Path) -> CostTracker:
    config = CostConfig(
        monthly_budget=1.0,
        max_cost_per_call=0.01,
        over_budget_action="warn",
    )
    return CostTracker(config, cost_file)


@pytest.fixture
def blocking_tracker(cost_file: Path) -> CostTracker:
    config = CostConfig(
        monthly_budget=1.0,
        max_cost_per_call=0.01,
        over_budget_action="block",
    )
    return CostTracker(config, cost_file)


class TestRecordUsage:
    def test_creates_file_and_appends_entry(self, tracker: CostTracker, cost_file: Path):
        cost = tracker.record_usage(1000, 500)
        assert cost_file.exists()
        lines = cost_file.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["input_tokens"] == 1000
        assert entry["output_tokens"] == 500
        assert entry["date"] == date.today().isoformat()
        assert cost > 0

    def test_multiple_entries(self, tracker: CostTracker, cost_file: Path):
        tracker.record_usage(1000, 500)
        tracker.record_usage(2000, 1000)
        lines = cost_file.read_text().strip().splitlines()
        assert len(lines) == 2

    def test_cost_calculation(self, tracker: CostTracker):
        # 1000 input * 0.15/1M + 500 output * 0.30/1M
        cost = tracker.record_usage(1000, 500)
        expected = (1000 * 0.15 / 1_000_000) + (500 * 0.30 / 1_000_000)
        assert abs(cost - expected) < 1e-10

    def test_zero_tokens(self, tracker: CostTracker):
        cost = tracker.record_usage(0, 0)
        assert cost == 0.0


class TestGetMonthlySpend:
    def test_empty_file(self, tracker: CostTracker):
        assert tracker.get_monthly_spend() == 0.0

    def test_missing_file(self, tracker: CostTracker, cost_file: Path):
        assert not cost_file.exists()
        assert tracker.get_monthly_spend() == 0.0

    def test_sums_current_month(self, tracker: CostTracker):
        tracker.record_usage(1000, 500)
        tracker.record_usage(2000, 1000)
        spend = tracker.get_monthly_spend()
        cost1 = (1000 * 0.15 / 1_000_000) + (500 * 0.30 / 1_000_000)
        cost2 = (2000 * 0.15 / 1_000_000) + (1000 * 0.30 / 1_000_000)
        assert abs(spend - (cost1 + cost2)) < 1e-10

    def test_ignores_old_months(self, cost_file: Path):
        config = CostConfig()
        t = CostTracker(config, cost_file)
        # Write an entry from last month
        old_entry = {
            "date": "2020-01-15",
            "input_tokens": 100000,
            "output_tokens": 100000,
            "cost": 99.0,
        }
        cost_file.write_text(json.dumps(old_entry) + "\n")
        assert t.get_monthly_spend() == 0.0

    def test_ignores_corrupt_lines(self, tracker: CostTracker, cost_file: Path):
        tracker.record_usage(1000, 500)
        with open(cost_file, "a") as f:
            f.write("not json\n")
            f.write("\n")
        spend = tracker.get_monthly_spend()
        expected = (1000 * 0.15 / 1_000_000) + (500 * 0.30 / 1_000_000)
        assert abs(spend - expected) < 1e-10


class TestCheckBeforeCall:
    def test_allows_reasonable_call(self, tracker: CostTracker):
        # 100 tokens * 20 bytes ~= tiny cost, well under limits
        assert tracker.check_before_call(100) is True

    def test_warns_on_large_call_but_returns_true(self, tracker: CostTracker):
        # Force a huge estimated cost: 1M tokens
        # estimated cost = 1M * 0.15/1M + 3M * 0.30/1M = 0.15 + 0.90 = 1.05
        # That exceeds max_cost_per_call=0.01 AND monthly_budget=1.0
        assert tracker.check_before_call(1_000_000) is True  # warn mode

    def test_blocks_on_per_call_limit(self, blocking_tracker: CostTracker):
        # Estimated cost ~ $1.05 > max_cost_per_call $0.01
        assert blocking_tracker.check_before_call(1_000_000) is False

    def test_blocks_on_monthly_budget(self, blocking_tracker: CostTracker, cost_file: Path):
        # Record enough to nearly exhaust the monthly budget
        # Monthly budget is $1.0, write a fake entry for $0.99
        fake = {
            "date": date.today().isoformat(),
            "input_tokens": 3_000_000,
            "output_tokens": 1_500_000,
            "cost": 0.99,
        }
        cost_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cost_file, "w") as f:
            f.write(json.dumps(fake) + "\n")
        # Even a modest call should exceed the remaining $0.01 budget
        # 1000 tokens -> est 1000*0.15/1M + 3000*0.30/1M = $0.00105, well under per-call
        # But $0.99 + $0.00105 = $0.991 < $1.0, so still within budget. Use bigger call.
        # 1M tokens -> est $1.05, $0.99 + $1.05 > $1.0 => blocked
        assert blocking_tracker.check_before_call(1_000_000) is False

    def test_allows_when_under_budget(self, blocking_tracker: CostTracker):
        # No spend recorded, small call
        assert blocking_tracker.check_before_call(100) is True

    def test_warn_mode_always_returns_true(self, tracker: CostTracker):
        # Even when way over budget, warn mode returns True
        assert tracker.check_before_call(100_000_000) is True


class TestGetStats:
    def test_empty_stats(self, tracker: CostTracker):
        stats = tracker.get_stats()
        assert stats["monthly_spend"] == 0.0
        assert stats["total_calls"] == 0
        assert stats["total_input_tokens"] == 0
        assert stats["total_output_tokens"] == 0
        assert stats["budget_remaining"] == 1.0

    def test_stats_after_usage(self, tracker: CostTracker):
        tracker.record_usage(1500, 800)
        tracker.record_usage(500, 200)
        stats = tracker.get_stats()
        assert stats["total_calls"] == 2
        assert stats["total_input_tokens"] == 2000
        assert stats["total_output_tokens"] == 1000
        assert stats["monthly_spend"] > 0
        assert stats["budget_remaining"] < 1.0

    def test_stats_includes_config(self, tracker: CostTracker):
        stats = tracker.get_stats()
        assert stats["max_cost_per_call"] == 0.01
        assert stats["monthly_budget"] == 1.0
        assert stats["over_budget_action"] == "warn"


class TestEdgeCases:
    def test_creates_parent_directory(self, tmp_path: Path):
        cost_file = tmp_path / "deep" / "nested" / "cost.jsonl"
        config = CostConfig()
        tracker = CostTracker(config, cost_file)
        tracker.record_usage(100, 50)
        assert cost_file.exists()

    def test_default_cost_file_path(self):
        config = CostConfig()
        tracker = CostTracker(config)
        assert tracker._cost_file == Path.home() / ".taxo" / "cost.jsonl"
