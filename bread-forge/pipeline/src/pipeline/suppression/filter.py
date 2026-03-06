"""Filter findings against active suppressions."""

from __future__ import annotations

from beads.store import BeadStore
from beads.types import FindingBead


class SuppressionsFilter:
    """Remove findings whose ID matches an active suppression's finding_class prefix.

    Args:
        store: BeadStore used to retrieve active suppressions.
    """

    def __init__(self, store: BeadStore) -> None:
        self._store = store

    def filter(
        self,
        findings: list[FindingBead],
        repo: str | None = None,
    ) -> list[FindingBead]:
        """Return *findings* with suppressed entries removed.

        A finding is suppressed when its ``id`` starts with the
        ``finding_class`` of any currently active suppression.  Active
        suppressions are fetched from the store; suppressions whose
        ``expires_at`` is in the past are excluded automatically by
        :meth:`~beads.store.BeadStore.list_active_suppressions`.

        Args:
            findings: Findings to filter.
            repo: When provided, restricts active suppressions to those
                recorded for this repository.

        Returns:
            A new list containing only the findings that are not suppressed.
        """
        active_suppressions = self._store.list_active_suppressions(repo=repo)
        if not active_suppressions:
            return list(findings)
        prefixes = [s.finding_class for s in active_suppressions]
        return [f for f in findings if not any(f.id.startswith(p) for p in prefixes)]
