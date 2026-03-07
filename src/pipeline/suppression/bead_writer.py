"""Write SuppressionBead to store on gate reject or defer."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from beads.store import BeadStore
from beads.types import SuppressionBead


def _derive_finding_class(finding_ids: list[str]) -> str:
    """Derive a finding_class prefix from one or more finding IDs.

    Returns the longest common character prefix of all provided IDs.
    This prefix is stored as the suppression's ``finding_class`` so that
    the filter can suppress any finding whose ID starts with the class.

    Args:
        finding_ids: Non-empty list of finding IDs to suppress.

    Returns:
        The longest common prefix shared by all *finding_ids*.

    Raises:
        ValueError: If *finding_ids* is empty.
    """
    if not finding_ids:
        raise ValueError("finding_ids must not be empty")
    first = finding_ids[0]
    for i, char in enumerate(first):
        for other in finding_ids[1:]:
            if i >= len(other) or other[i] != char:
                return first[:i]
    return first


def write_suppression(
    store: BeadStore,
    finding_ids: list[str],
    decision: Literal["rejected", "deferred"],
    reason: str,
    created_by: str,
    expires_at: datetime | None = None,
) -> SuppressionBead:
    """Create and persist a SuppressionBead derived from *finding_ids*.

    The suppression's ``finding_class`` is computed as the longest common
    prefix of all provided *finding_ids*.  The filter layer later uses this
    prefix to suppress any finding whose ``id`` starts with it.

    Args:
        store: BeadStore to write the suppression to.
        finding_ids: IDs of the findings being suppressed (non-empty).
        decision: Gate outcome that triggered the suppression
            (``"rejected"`` or ``"deferred"``).
        reason: Human-readable explanation for the suppression.
        created_by: Identity of the reviewer creating the suppression.
        expires_at: When the suppression expires.  ``None`` means it never
            expires.  If set to a past datetime the suppression is
            immediately inactive.

    Returns:
        The :class:`~beads.types.SuppressionBead` that was written to *store*.

    Raises:
        ValueError: If *finding_ids* is empty.
    """
    finding_class = _derive_finding_class(finding_ids)
    bead = SuppressionBead(
        suppression_id=str(uuid.uuid4()),
        finding_class=finding_class,
        decision=decision,
        reason=reason,
        created_by=created_by,
        created_at=datetime.now(UTC),
        expires_at=expires_at,
    )
    store.write_suppression(bead)
    return bead
