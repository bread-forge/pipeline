"""GateActions: approve, reject, and defer gate proposals."""

from __future__ import annotations

from datetime import UTC, datetime

from beads.store import BeadStore
from beads.types import ProposalBead

from pipeline.events.log import EventLog
from pipeline.events.types import GateDecision
from pipeline.suppression.bead_writer import write_suppression


class GateActions:
    """Update ProposalBead status and record GateDecision events.

    On reject or defer, a SuppressionBead is persisted via
    :func:`~pipeline.suppression.bead_writer.write_suppression` when
    *finding_ids* are supplied to those methods.

    Args:
        store: BeadStore used to read and write ProposalBead objects.
        event_log: Optional EventLog; if None, no events are appended.
        created_by: Identity of the reviewer making gate decisions.
            Used as the ``created_by`` field on suppression beads.
    """

    def __init__(
        self,
        store: BeadStore,
        event_log: EventLog | None = None,
        created_by: str = "",
    ) -> None:
        self._store = store
        self._event_log = event_log
        self._created_by = created_by

    def _load_proposal(self, proposal_id: str) -> ProposalBead:
        bead = self._store.read_proposal(proposal_id)
        if bead is None:
            raise KeyError(f"Proposal not found: {proposal_id!r}")
        return bead

    def approve(self, proposal_id: str, review_seconds: float | None) -> None:
        """Approve a proposal and record the gate decision.

        Sets status to ``"approved"``, stamps ``gate_decision_at``, and appends
        a :class:`~pipeline.events.types.GateDecision` event with
        ``approved=True``.

        Args:
            proposal_id: ID of the proposal to approve.
            review_seconds: Seconds the reviewer spent on the proposal (or None).

        Raises:
            KeyError: If no proposal exists for *proposal_id*.
        """
        now = datetime.now(UTC)
        bead = self._load_proposal(proposal_id)
        bead.status = "approved"
        bead.gate_decision_at = now
        bead.review_seconds = review_seconds
        self._store.write_proposal(bead)
        if self._event_log is not None:
            self._event_log.append(
                GateDecision(
                    cycle_id=bead.cycle_id,
                    timestamp=now,
                    approved=True,
                    reason="",
                )
            )

    def reject(
        self,
        proposal_id: str,
        reason: str,
        review_seconds: float | None,
        finding_ids: list[str] | None = None,
    ) -> None:
        """Reject a proposal and record the gate decision with a reason.

        Sets status to ``"rejected"``, stamps ``gate_decision_at``, and appends
        a :class:`~pipeline.events.types.GateDecision` event with
        ``approved=False``.  When *finding_ids* is provided and non-empty, a
        permanent :class:`~beads.types.SuppressionBead` is persisted so that
        future cycles suppress these findings automatically.

        Args:
            proposal_id: ID of the proposal to reject.
            reason: Human-readable explanation for the rejection.
            review_seconds: Seconds the reviewer spent on the proposal (or None).
            finding_ids: IDs of the findings to suppress permanently.  When
                ``None`` or empty, no suppression bead is written.

        Raises:
            KeyError: If no proposal exists for *proposal_id*.
        """
        now = datetime.now(UTC)
        bead = self._load_proposal(proposal_id)
        bead.status = "rejected"
        bead.gate_decision_at = now
        bead.review_seconds = review_seconds
        self._store.write_proposal(bead)
        if self._event_log is not None:
            self._event_log.append(
                GateDecision(
                    cycle_id=bead.cycle_id,
                    timestamp=now,
                    approved=False,
                    reason=reason,
                )
            )
        if finding_ids:
            write_suppression(
                self._store,
                finding_ids=finding_ids,
                decision="rejected",
                reason=reason,
                created_by=self._created_by,
                expires_at=None,
            )

    def defer(
        self,
        proposal_id: str,
        defer_until: datetime,
        review_seconds: float | None,
        finding_ids: list[str] | None = None,
    ) -> None:
        """Defer a proposal until a specified time.

        Sets status to ``"deferred"``, stamps ``gate_decision_at``, and appends
        a :class:`~pipeline.events.types.GateDecision` event with
        ``approved=False`` and a reason encoding the defer-until timestamp.
        When *finding_ids* is provided and non-empty, a
        :class:`~beads.types.SuppressionBead` expiring at *defer_until* is
        persisted so that these findings are suppressed until that date.

        Args:
            proposal_id: ID of the proposal to defer.
            defer_until: Earliest datetime at which the proposal may be reviewed.
            review_seconds: Seconds the reviewer spent on the proposal (or None).
            finding_ids: IDs of the findings to suppress until *defer_until*.
                When ``None`` or empty, no suppression bead is written.

        Raises:
            KeyError: If no proposal exists for *proposal_id*.
        """
        now = datetime.now(UTC)
        bead = self._load_proposal(proposal_id)
        bead.status = "deferred"
        bead.gate_decision_at = now
        bead.review_seconds = review_seconds
        self._store.write_proposal(bead)
        if self._event_log is not None:
            self._event_log.append(
                GateDecision(
                    cycle_id=bead.cycle_id,
                    timestamp=now,
                    approved=False,
                    reason=f"deferred until {defer_until.isoformat()}",
                )
            )
        if finding_ids:
            write_suppression(
                self._store,
                finding_ids=finding_ids,
                decision="deferred",
                reason=f"deferred until {defer_until.isoformat()}",
                created_by=self._created_by,
                expires_at=defer_until,
            )
