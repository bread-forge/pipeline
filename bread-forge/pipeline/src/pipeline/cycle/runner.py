"""CycleRunner: filter the proposal queue through active suppressions before gating."""

from __future__ import annotations

from beads.store import BeadStore
from beads.types import FindingBead

from pipeline.suppression.filter import SuppressionsFilter


class CycleRunner:
    """Orchestrate the gate phase of a pipeline cycle.

    Filters the proposal queue through active suppressions before handing
    findings to the gate for human review.  A finding is removed from the
    queue when it matches an active suppression recorded by a previous
    reject or defer decision.

    Args:
        store: BeadStore used to load active suppressions.
    """

    def __init__(self, store: BeadStore) -> None:
        self._store = store
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
