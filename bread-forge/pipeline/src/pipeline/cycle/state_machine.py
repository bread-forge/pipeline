"""Cycle state machine — phase transitions with explicit completion criteria.

The state machine is stateless: all state lives in the :class:`beads.types.CycleBead`
that the caller persists.  Methods inspect replayed events to decide whether the
current phase is complete before advancing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from beads.types import CycleBead

from pipeline.cycle.phase import CyclePhase

# ---------------------------------------------------------------------------
# Event type
# ---------------------------------------------------------------------------

# Event types that mark a phase as complete when at least one is present.
_PHASE_COMPLETION_EVENT_TYPES: dict[CyclePhase, frozenset[str]] = {
    # ANALYSIS completes when findings exist OR when all dispatched agents report
    # completion (allowing zero-finding cycles to still advance to synthesis).
    CyclePhase.ANALYSIS: frozenset({"finding_added", "all_agents_completed"}),
    CyclePhase.SYNTHESIS: frozenset({"proposal_added"}),
    CyclePhase.GATE: frozenset({"proposal_approved"}),
    CyclePhase.EXECUTION: frozenset({"execution_completed"}),
    CyclePhase.VERIFICATION: frozenset({"verification_passed"}),
}


@dataclass(frozen=True)
class CycleEvent:
    """A single replayed event from the pipeline event log.

    The ``event_type`` string matches one of the keys in
    ``_PHASE_COMPLETION_EVENT_TYPES`` to signal phase completion.
    ``metadata`` carries arbitrary context (issue numbers, costs, etc.) that
    callers may inspect but the state machine does not require.
    """

    event_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class InvalidPhaseTransitionError(Exception):
    """Raised when a requested phase transition is not allowed."""


class CycleStateMachine:
    """Evaluates cycle phase transitions by inspecting replayed events.

    All methods are pure (no I/O).  Persistence is handled by the caller via
    :func:`pipeline.cycle.bead.write_phase_transition`.

    Usage::

        sm = CycleStateMachine()
        events = [CycleEvent("finding_added"), ...]
        if sm.can_advance(CyclePhase.ANALYSIS, events):
            bead = sm.advance(bead, store, events)
    """

    def can_advance(self, phase: CyclePhase, events: Sequence[CycleEvent]) -> bool:
        """Return True if *phase* has met its completion criteria in *events*.

        :class:`CyclePhase.NEXT_CYCLE` has no further transition; always returns
        False.

        Args:
            phase: The current cycle phase.
            events: All events replayed for the current cycle, in any order.

        Returns:
            True when at least one event with a completion event type for *phase*
            is present.  False when the phase is already terminal or no
            completion event exists yet.
        """
        required = _PHASE_COMPLETION_EVENT_TYPES.get(phase)
        if required is None:
            # NEXT_CYCLE is terminal — no further advance is possible.
            return False
        observed_types = {e.event_type for e in events}
        return bool(required & observed_types)

    def next_phase(self, phase: CyclePhase) -> CyclePhase | None:
        """Return the phase that follows *phase*, or None if *phase* is terminal.

        Args:
            phase: Current phase.

        Returns:
            The successor :class:`CyclePhase`, or None when *phase* is
            :attr:`CyclePhase.NEXT_CYCLE`.
        """
        ordered = CyclePhase.ordered()
        idx = ordered.index(phase)
        next_idx = idx + 1
        if next_idx >= len(ordered):
            return None
        return ordered[next_idx]

    def current_phase_from_bead(self, bead: CycleBead) -> CyclePhase:
        """Deserialise the phase stored in *bead* into a :class:`CyclePhase`.

        Args:
            bead: The cycle bead whose ``phase`` field to read.

        Returns:
            The matching :class:`CyclePhase` enum member.

        Raises:
            ValueError: When ``bead.phase`` does not match any known phase.
        """
        try:
            return CyclePhase(bead.phase)
        except ValueError as err:
            raise ValueError(
                f"Unknown phase value {bead.phase!r} in bead {bead.cycle_id!r}"
            ) from err

    def advance(
        self,
        bead: CycleBead,
        events: Sequence[CycleEvent],
    ) -> CyclePhase:
        """Compute the next phase for *bead* given *events*.

        Does NOT write to any store — the caller is responsible for persistence
        via :func:`pipeline.cycle.bead.write_phase_transition`.

        Args:
            bead: The cycle bead representing current state.
            events: All events replayed for the current cycle.

        Returns:
            The :class:`CyclePhase` to transition into.

        Raises:
            InvalidPhaseTransitionError: When the current phase has not yet met
                its completion criteria or is already terminal.
        """
        current = self.current_phase_from_bead(bead)
        if not self.can_advance(current, events):
            raise InvalidPhaseTransitionError(
                f"Phase {current.value!r} is not complete — "
                f"required event types: "
                f"{_PHASE_COMPLETION_EVENT_TYPES.get(current, frozenset())!r}"
            )
        successor = self.next_phase(current)
        if successor is None:
            raise InvalidPhaseTransitionError(
                f"Phase {current.value!r} is terminal; no successor phase exists."
            )
        return successor
