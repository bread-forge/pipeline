"""BudgetTracker — per-cycle USD cost accumulator with optional cap enforcement."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from pipeline.events.types import BudgetExceeded


class BudgetTracker:
    """Accumulates USD cost per cycle and enforces an optional spending cap.

    Instantiate once per cycle. Call ``record_cost`` after each agent run to
    accumulate spend. Call ``is_exceeded`` before each dispatch to check whether
    the cycle has already breached a given limit.

    If the tracker was constructed with a ``cap_usd``, ``record_cost`` will raise
    ``BudgetExceeded`` as soon as the running total crosses that cap.
    """

    def __init__(
        self,
        cycle_id: str,
        cap_usd: float | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """
        Args:
            cycle_id: Identifier for the current pipeline cycle.
            cap_usd: Hard spending cap. When set, ``record_cost`` raises
                ``BudgetExceeded`` as soon as cumulative spend exceeds this value.
                ``None`` means no automatic enforcement — callers use
                ``is_exceeded`` to check against their own limits.
            clock: Callable that returns the current UTC datetime. Injected for
                deterministic testing; defaults to ``datetime.now(UTC)``.
        """
        self._cycle_id = cycle_id
        self._cap_usd = cap_usd
        self._clock: Callable[[], datetime] = (
            clock if clock is not None else lambda: datetime.now(UTC)
        )
        self._total_usd: float = 0.0

    @property
    def total_usd(self) -> float:
        """Running total of all recorded costs for this cycle."""
        return self._total_usd

    def record_cost(self, agent_id: str, cost_usd: float) -> None:
        """Add ``cost_usd`` to the running total for ``agent_id``.

        Args:
            agent_id: Identifier of the agent whose cost is being recorded.
            cost_usd: Cost in USD to add (must be non-negative).

        Raises:
            ValueError: If ``cost_usd`` is negative.
            BudgetExceeded: If the tracker has a ``cap_usd`` and the new total
                exceeds it.
        """
        if cost_usd < 0:
            raise ValueError(f"cost_usd must be non-negative, got {cost_usd}")

        self._total_usd += cost_usd

        if self._cap_usd is not None and self._total_usd > self._cap_usd:
            raise BudgetExceeded(
                cycle_id=self._cycle_id,
                timestamp=self._clock(),
                agent_id=agent_id,
                total_usd=self._total_usd,
                limit_usd=self._cap_usd,
            )

    def is_exceeded(self, limit_usd: float) -> bool:
        """Return ``True`` if the running total has surpassed ``limit_usd``.

        Use this before dispatching an agent to gate on any per-cycle budget
        without needing a hard cap on the tracker itself.

        Args:
            limit_usd: The limit to check the running total against.
        """
        return self._total_usd > limit_usd
