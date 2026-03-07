"""Tests for pipeline.budget.tracker — BudgetTracker cost accumulation and cap enforcement."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipeline.budget.tracker import BudgetTracker
from pipeline.events.types import BudgetExceeded

CYCLE_ID = "cycle-budget-test"
FIXED_TIME = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
FIXED_CLOCK = lambda: FIXED_TIME  # noqa: E731


# ---------------------------------------------------------------------------
# BudgetTracker.total_usd property
# ---------------------------------------------------------------------------


class TestTotalUsdProperty:
    """BudgetTracker.total_usd reflects the running accumulated cost."""

    def test_initial_total_is_zero(self) -> None:
        """A freshly constructed tracker starts at 0.0."""
        tracker = BudgetTracker(cycle_id=CYCLE_ID)
        assert tracker.total_usd == 0.0

    def test_total_reflects_single_record(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID)
        tracker.record_cost("agent-a", 1.25)
        assert tracker.total_usd == 1.25

    def test_total_accumulates_across_multiple_calls(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID)
        tracker.record_cost("agent-a", 0.50)
        tracker.record_cost("agent-b", 0.30)
        tracker.record_cost("agent-c", 0.20)
        assert tracker.total_usd == pytest.approx(1.0)

    def test_zero_cost_does_not_change_total(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID)
        tracker.record_cost("agent-a", 0.0)
        assert tracker.total_usd == 0.0


# ---------------------------------------------------------------------------
# BudgetTracker.record_cost — happy path
# ---------------------------------------------------------------------------


class TestRecordCost:
    """record_cost accumulates costs and optionally enforces a cap."""

    def test_accumulates_different_agents(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID)
        tracker.record_cost("agent-x", 1.00)
        tracker.record_cost("agent-y", 2.00)
        assert tracker.total_usd == pytest.approx(3.00)

    def test_accumulates_same_agent_multiple_times(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID)
        tracker.record_cost("agent-a", 0.10)
        tracker.record_cost("agent-a", 0.10)
        tracker.record_cost("agent-a", 0.10)
        assert tracker.total_usd == pytest.approx(0.30)

    def test_small_fractional_amounts_accumulate(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID)
        for _ in range(10):
            tracker.record_cost("agent-a", 0.001)
        assert tracker.total_usd == pytest.approx(0.01)

    def test_no_cap_never_raises_budget_exceeded(self) -> None:
        """Without a cap, record_cost never raises BudgetExceeded."""
        tracker = BudgetTracker(cycle_id=CYCLE_ID, cap_usd=None)
        for _ in range(100):
            tracker.record_cost("agent-a", 999.99)
        # No exception raised.
        assert tracker.total_usd > 0.0


# ---------------------------------------------------------------------------
# BudgetTracker.record_cost — validation errors
# ---------------------------------------------------------------------------


class TestRecordCostValidation:
    """record_cost rejects invalid inputs before updating any state."""

    def test_negative_cost_raises_value_error(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID)
        with pytest.raises(ValueError, match="non-negative"):
            tracker.record_cost("agent-a", -0.01)

    def test_negative_cost_does_not_change_total(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID)
        tracker.record_cost("agent-a", 1.00)
        with pytest.raises(ValueError):
            tracker.record_cost("agent-a", -0.50)
        # Total must remain unchanged after the failed call.
        assert tracker.total_usd == pytest.approx(1.00)

    def test_very_negative_cost_raises_value_error(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID)
        with pytest.raises(ValueError):
            tracker.record_cost("agent-a", -1_000_000.0)


# ---------------------------------------------------------------------------
# BudgetTracker.record_cost — cap enforcement and BudgetExceeded
# ---------------------------------------------------------------------------


class TestCapEnforcement:
    """When cap_usd is set, record_cost raises BudgetExceeded on breach."""

    def test_below_cap_does_not_raise(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID, cap_usd=10.0, clock=FIXED_CLOCK)
        tracker.record_cost("agent-a", 9.99)
        # No exception.
        assert tracker.total_usd == pytest.approx(9.99)

    def test_exactly_at_cap_does_not_raise(self) -> None:
        """Equality to cap is allowed; only strictly exceeding triggers the error."""
        tracker = BudgetTracker(cycle_id=CYCLE_ID, cap_usd=5.0, clock=FIXED_CLOCK)
        tracker.record_cost("agent-a", 5.0)
        assert tracker.total_usd == pytest.approx(5.0)

    def test_exceeding_cap_raises_budget_exceeded(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID, cap_usd=1.0, clock=FIXED_CLOCK)
        with pytest.raises(BudgetExceeded):
            tracker.record_cost("agent-a", 1.01)

    def test_budget_exceeded_event_has_correct_cycle_id(self) -> None:
        tracker = BudgetTracker(cycle_id="my-cycle", cap_usd=1.0, clock=FIXED_CLOCK)
        with pytest.raises(BudgetExceeded) as exc_info:
            tracker.record_cost("agent-a", 2.0)
        assert exc_info.value.cycle_id == "my-cycle"

    def test_budget_exceeded_event_has_correct_agent_id(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID, cap_usd=1.0, clock=FIXED_CLOCK)
        with pytest.raises(BudgetExceeded) as exc_info:
            tracker.record_cost("the-breaching-agent", 5.0)
        assert exc_info.value.agent_id == "the-breaching-agent"

    def test_budget_exceeded_event_has_correct_total_usd(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID, cap_usd=1.0, clock=FIXED_CLOCK)
        tracker.record_cost("agent-a", 0.50)
        with pytest.raises(BudgetExceeded) as exc_info:
            tracker.record_cost("agent-b", 1.00)
        assert exc_info.value.total_usd == pytest.approx(1.50)

    def test_budget_exceeded_event_has_correct_limit_usd(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID, cap_usd=2.50, clock=FIXED_CLOCK)
        with pytest.raises(BudgetExceeded) as exc_info:
            tracker.record_cost("agent-a", 3.0)
        assert exc_info.value.limit_usd == pytest.approx(2.50)

    def test_budget_exceeded_event_has_correct_timestamp(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID, cap_usd=1.0, clock=FIXED_CLOCK)
        with pytest.raises(BudgetExceeded) as exc_info:
            tracker.record_cost("agent-a", 2.0)
        assert exc_info.value.timestamp == FIXED_TIME

    def test_budget_exceeded_event_type_field(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID, cap_usd=1.0, clock=FIXED_CLOCK)
        with pytest.raises(BudgetExceeded) as exc_info:
            tracker.record_cost("agent-a", 2.0)
        assert exc_info.value.event_type == "BudgetExceeded"

    def test_budget_exceeded_is_also_an_exception(self) -> None:
        """BudgetExceeded inherits from Exception for try/except usage."""
        event = BudgetExceeded(
            cycle_id=CYCLE_ID,
            timestamp=FIXED_TIME,
            agent_id="agent-a",
            total_usd=2.0,
            limit_usd=1.0,
        )
        assert isinstance(event, Exception)

    def test_cumulative_spend_breaches_cap(self) -> None:
        """Multiple small costs that together exceed the cap trigger the error."""
        tracker = BudgetTracker(cycle_id=CYCLE_ID, cap_usd=1.0, clock=FIXED_CLOCK)
        tracker.record_cost("agent-a", 0.40)
        tracker.record_cost("agent-b", 0.40)
        with pytest.raises(BudgetExceeded):
            tracker.record_cost("agent-c", 0.30)

    def test_total_includes_breaching_cost_when_raised(self) -> None:
        """The total is updated before the exception is raised."""
        tracker = BudgetTracker(cycle_id=CYCLE_ID, cap_usd=1.0, clock=FIXED_CLOCK)
        with pytest.raises(BudgetExceeded):
            tracker.record_cost("agent-a", 1.50)
        assert tracker.total_usd == pytest.approx(1.50)


# ---------------------------------------------------------------------------
# BudgetTracker.is_exceeded
# ---------------------------------------------------------------------------


class TestIsExceeded:
    """is_exceeded returns True only when total strictly exceeds the given limit."""

    def test_false_when_total_is_zero(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID)
        assert tracker.is_exceeded(0.01) is False

    def test_false_when_total_below_limit(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID)
        tracker.record_cost("agent-a", 0.50)
        assert tracker.is_exceeded(1.00) is False

    def test_false_when_total_equals_limit(self) -> None:
        """Equal-to-limit is NOT exceeded."""
        tracker = BudgetTracker(cycle_id=CYCLE_ID)
        tracker.record_cost("agent-a", 1.00)
        assert tracker.is_exceeded(1.00) is False

    def test_true_when_total_exceeds_limit(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID)
        tracker.record_cost("agent-a", 1.01)
        assert tracker.is_exceeded(1.00) is True

    def test_independent_of_cap_usd(self) -> None:
        """is_exceeded checks against its own argument, not the tracker's cap."""
        tracker = BudgetTracker(cycle_id=CYCLE_ID, cap_usd=100.0)
        tracker.record_cost("agent-a", 5.0)
        assert tracker.is_exceeded(4.99) is True
        assert tracker.is_exceeded(5.01) is False

    def test_false_limit_of_zero_with_zero_total(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID)
        assert tracker.is_exceeded(0.0) is False

    def test_true_when_limit_is_zero_and_any_cost_recorded(self) -> None:
        tracker = BudgetTracker(cycle_id=CYCLE_ID)
        tracker.record_cost("agent-a", 0.001)
        assert tracker.is_exceeded(0.0) is True


# ---------------------------------------------------------------------------
# Clock injection
# ---------------------------------------------------------------------------


class TestClockInjection:
    """The clock parameter enables deterministic timestamp testing."""

    def test_custom_clock_used_in_budget_exceeded_timestamp(self) -> None:
        custom_time = datetime(2099, 6, 15, 10, 30, 0, tzinfo=UTC)
        clock = lambda: custom_time  # noqa: E731
        tracker = BudgetTracker(cycle_id=CYCLE_ID, cap_usd=1.0, clock=clock)
        with pytest.raises(BudgetExceeded) as exc_info:
            tracker.record_cost("agent-a", 2.0)
        assert exc_info.value.timestamp == custom_time

    def test_default_clock_uses_utc(self) -> None:
        """Without injection, the timestamp is a UTC-aware datetime."""
        tracker = BudgetTracker(cycle_id=CYCLE_ID, cap_usd=0.01)
        with pytest.raises(BudgetExceeded) as exc_info:
            tracker.record_cost("agent-a", 1.0)
        assert exc_info.value.timestamp.tzinfo is not None
