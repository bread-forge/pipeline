"""CycleRunner: analysis orchestration with budget tracking and telemetry."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from pathlib import Path

from beads.store import BeadStore
from beads.types import CycleBead, FindingBead

from pipeline.budget.tracker import BudgetTracker
from pipeline.cycle.phase import CyclePhase
from pipeline.dispatch.agent import AgentDispatcher
from pipeline.events.log import EventLog
from pipeline.suppression.filter import SuppressionsFilter
from pipeline.telemetry.metrics import compute_cycle_metrics
from pipeline.telemetry.store import TelemetryStore


class CycleRunner:
    """Orchestrate the analysis phase of a pipeline cycle.

    Filters the proposal queue through active suppressions before handing
    findings to the gate for human review.  Also runs the analysis phase
    with budget tracking via :meth:`run`, and records per-cycle telemetry
    when a cycle reaches completion.

    Args:
        store: BeadStore used to load active suppressions and read proposals.
        max_analysis_cost: Optional USD spending cap for a single analysis
            cycle.  Passed to :class:`~pipeline.budget.tracker.BudgetTracker`
            as the ``cap_usd``.  ``None`` means no cap is enforced.
        telemetry_store: When provided, cycle metrics are appended here at
            the start of :meth:`run` if the bead is already in the
            ``NEXT_CYCLE`` (complete) phase.
    """

    def __init__(
        self,
        store: BeadStore,
        max_analysis_cost: float | None = None,
        telemetry_store: TelemetryStore | None = None,
    ) -> None:
        self._store = store
        self._max_analysis_cost = max_analysis_cost
        self._telemetry_store = telemetry_store
        self._suppression_filter = SuppressionsFilter(store)

    def filter_proposals(
        self,
        proposals: list[FindingBead],
        repo: str | None = None,
    ) -> list[FindingBead]:
        """Return *proposals* with actively suppressed findings removed.

        Delegates to :class:`~pipeline.suppression.filter.SuppressionsFilter`
        to check each finding against the current set of active suppressions.
        Suppressions whose ``expires_at`` is in the past are excluded
        automatically by the store.

        Args:
            proposals: Findings queued for gate review.
            repo: When provided, restricts active suppressions to those
                recorded for this repository.

        Returns:
            A new list containing only the proposals that are not suppressed.
        """
        return self._suppression_filter.filter(proposals, repo=repo)

    def run(
        self,
        cycle_id: str,
        bead: CycleBead,
        agent_names: Sequence[str],
        repo_path: Path,
        event_log: EventLog,
    ) -> list[FindingBead]:
        """Run the analysis phase of a cycle with budget tracking.

        If *bead* is already in the :attr:`~pipeline.cycle.phase.CyclePhase.NEXT_CYCLE`
        (complete) phase and a ``telemetry_store`` was provided at construction,
        cycle metrics are computed and appended to the store before returning.

        Otherwise, a :class:`~pipeline.budget.tracker.BudgetTracker` is created
        from ``max_analysis_cost`` and passed to
        :class:`~pipeline.dispatch.agent.AgentDispatcher`, which runs each agent
        in order, recording costs and enforcing the cap.

        Args:
            cycle_id: Identifier of the current cycle.
            bead: The current :class:`~beads.types.CycleBead`.  Modified in
                place when the phase advances to SYNTHESIS.
            agent_names: Ordered sequence of agent identifiers to dispatch.
            repo_path: Absolute path to the repository root.
            event_log: Event log for this cycle.

        Returns:
            All :class:`~beads.types.FindingBead` objects collected after
            agents complete.  Empty list when the bead was already complete.
        """
        if bead.phase == CyclePhase.NEXT_CYCLE and self._telemetry_store is not None:
            self._record_telemetry(bead)
            return []

        budget_tracker = BudgetTracker(cycle_id, cap_usd=self._max_analysis_cost)
        dispatcher = AgentDispatcher(
            cycle_id=cycle_id,
            repo=bead.repo,
            store=self._store,
            event_log=event_log,
            budget_tracker=budget_tracker,
        )
        return dispatcher.dispatch(agent_names, repo_path, bead)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _record_telemetry(self, bead: CycleBead) -> None:
        """Compute cycle metrics and append them to the telemetry store.

        Reads proposals and active suppressions for the cycle's repo from the
        store, delegates metric computation to
        :func:`~pipeline.telemetry.metrics.compute_cycle_metrics`, and appends
        the result as a plain dict to :attr:`_telemetry_store`.
        """
        all_proposals = self._store.list_proposals(repo=bead.repo)
        cycle_proposals = [p for p in all_proposals if p.cycle_id == bead.cycle_id]
        suppressions = self._store.list_active_suppressions(repo=bead.repo)
        metrics = compute_cycle_metrics(bead, cycle_proposals, suppressions)
        assert self._telemetry_store is not None  # guard: caller checked before invoking
        self._telemetry_store.append(dataclasses.asdict(metrics))
