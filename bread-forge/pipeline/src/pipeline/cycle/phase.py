"""Cycle phase definitions."""

from enum import Enum


class CyclePhase(str, Enum):
    """Ordered phases of a single pipeline cycle.

    Values match the ``phase`` field of :class:`beads.types.CycleBead` so that
    ``phase.value`` can be assigned directly without a separate mapping.
    """

    ANALYSIS = "analysis"
    """Findings are collected from repo-audit agents."""

    SYNTHESIS = "synthesis"
    """Findings are condensed into spec proposals."""

    GATE = "gate"
    """Proposals await human review and approval/rejection."""

    EXECUTION = "execution"
    """Approved proposals are dispatched to build agents."""

    VERIFICATION = "verification"
    """Completed builds are checked for correctness and coverage."""

    NEXT_CYCLE = "complete"
    """All verification passed — cycle is complete; the next cycle may begin."""

    # Iteration order defines the valid progression.
    @classmethod
    def ordered(cls) -> list["CyclePhase"]:
        """Return phases in their canonical execution order."""
        return [
            cls.ANALYSIS,
            cls.SYNTHESIS,
            cls.GATE,
            cls.EXECUTION,
            cls.VERIFICATION,
            cls.NEXT_CYCLE,
        ]
