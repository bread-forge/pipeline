"""Cycle bead access and phase-transition writer.

Re-exports :class:`beads.types.CycleBead` so that callers import the type from
this module rather than from ``beads`` directly.  Also provides
:func:`write_phase_transition`, the single function responsible for advancing a
bead's phase and persisting it atomically to the store.
"""

from beads.store import BeadStore
from beads.types import CycleBead

from pipeline.cycle.phase import CyclePhase

__all__ = ["CycleBead", "write_phase_transition"]


def write_phase_transition(
    store: BeadStore,
    bead: CycleBead,
    new_phase: CyclePhase,
) -> CycleBead:
    """Transition *bead* to *new_phase* and persist it atomically to *store*.

    The function mutates *bead* in place and returns it so callers can chain
    calls::

        bead = write_phase_transition(store, bead, CyclePhase.SYNTHESIS)

    :meth:`BeadStore.write_cycle` calls ``bead.touch()`` internally, so
    ``updated_at`` is always refreshed on disk even if the caller does not call
    ``touch()`` first.

    Args:
        store: BeadStore to write to.
        bead: Cycle bead to update.  Modified in place.
        new_phase: Phase to transition into.

    Returns:
        The updated bead (same object, mutated).
    """
    bead.phase = new_phase.value
    store.write_cycle(bead)
    return bead
