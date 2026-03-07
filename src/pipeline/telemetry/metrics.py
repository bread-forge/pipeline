"""CycleMetrics: compute per-cycle telemetry metrics from bead data."""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from beads.types import CycleBead, ProposalBead, SuppressionBead

# Alert thresholds — named so callers can override without magic numbers.
REVIEW_TIME_THRESHOLD_SECONDS: float = 300.0  # 5 minutes
CONSECUTIVE_CYCLE_ALERT_COUNT: int = 3


@dataclass(frozen=True)
class CycleMetrics:
    """Metrics computed for a single completed pipeline cycle.

    Rates (``approval_rate``, ``rejection_rate``, ``deferral_rate``) are
    fractions in [0.0, 1.0] over the subset of proposals that received a
    gate decision.  When no decided proposals exist, all three are 0.0.
    ``median_review_seconds`` is ``None`` when no proposal has a recorded
    review time.
    """

    approval_rate: float
    rejection_rate: float
    deferral_rate: float
    median_review_seconds: float | None
    suppression_count: int
    total_analysis_cost_usd: float
    finding_count: int
    proposal_count: int


def compute_cycle_metrics(
    cycle: CycleBead,
    proposals: list[ProposalBead],
    suppressions: list[SuppressionBead],
) -> CycleMetrics:
    """Compute metrics for a single completed cycle.

    Args:
        cycle: The ``CycleBead`` for the completed cycle.  Provides
            ``finding_count``, ``proposal_count``, and ``total_cost_usd``.
        proposals: All ``ProposalBead`` objects for this cycle.  Gate
            decisions (approved/rejected/deferred) and review times are
            drawn from these.
        suppressions: Active ``SuppressionBead`` objects for this cycle's
            repo.  The count is reported directly; callers should pre-filter
            to only active suppressions if that is the desired semantics.

    Returns:
        A :class:`CycleMetrics` instance with all fields populated.
    """
    decided = [p for p in proposals if p.status in ("approved", "rejected", "deferred")]
    total_decided = len(decided)

    if total_decided > 0:
        approved = sum(1 for p in decided if p.status == "approved")
        rejected = sum(1 for p in decided if p.status == "rejected")
        deferred = sum(1 for p in decided if p.status == "deferred")
        approval_rate = approved / total_decided
        rejection_rate = rejected / total_decided
        deferral_rate = deferred / total_decided
    else:
        approval_rate = 0.0
        rejection_rate = 0.0
        deferral_rate = 0.0

    review_times = [p.review_seconds for p in proposals if p.review_seconds is not None]
    median_review_seconds: float | None = statistics.median(review_times) if review_times else None

    return CycleMetrics(
        approval_rate=approval_rate,
        rejection_rate=rejection_rate,
        deferral_rate=deferral_rate,
        median_review_seconds=median_review_seconds,
        suppression_count=len(suppressions),
        total_analysis_cost_usd=cycle.total_cost_usd,
        finding_count=cycle.finding_count,
        proposal_count=cycle.proposal_count,
    )


def check_review_time_alert(
    recent_metrics: list[CycleMetrics],
    threshold_seconds: float = REVIEW_TIME_THRESHOLD_SECONDS,
    consecutive_cycles: int = CONSECUTIVE_CYCLE_ALERT_COUNT,
) -> bool:
    """Return ``True`` when median review time has exceeded the threshold for
    ``consecutive_cycles`` cycles in a row.

    This triggers an alert telling the operator that gate review is becoming
    a bottleneck — the human reviewer is consistently taking more than 5
    minutes per cycle.

    Args:
        recent_metrics: Ordered list of :class:`CycleMetrics` (oldest first).
            Typically the full history for the repo read from
            :class:`~pipeline.telemetry.store.TelemetryStore`.
        threshold_seconds: Per-cycle alert threshold in seconds.
            Defaults to 300 (5 minutes).
        consecutive_cycles: How many consecutive cycles must all exceed the
            threshold before the alert fires.  Defaults to 3.

    Returns:
        ``True`` if the last *consecutive_cycles* entries all have a
        ``median_review_seconds`` above *threshold_seconds*.  ``False`` when
        there are fewer than *consecutive_cycles* data points or any cycle in
        the window is below the threshold or has no review-time data
        (``median_review_seconds is None``).
    """
    if len(recent_metrics) < consecutive_cycles:
        return False
    last_n = recent_metrics[-consecutive_cycles:]
    return all(
        m.median_review_seconds is not None and m.median_review_seconds > threshold_seconds
        for m in last_n
    )
