"""Tests for CycleStateMachine phase transitions."""

from __future__ import annotations

import pytest
from beads.types import CycleBead

from pipeline.cycle.phase import CyclePhase
from pipeline.cycle.state_machine import (
    CycleEvent,
    CycleStateMachine,
    InvalidPhaseTransitionError,
)


def _bead(phase: str) -> CycleBead:
    return CycleBead(cycle_id="test-cycle", repo="owner/repo", phase=phase)  # type: ignore[arg-type]


class TestCanAdvance:
    """Tests for CycleStateMachine.can_advance."""

    def test_returns_true_when_completion_event_present(self) -> None:
        sm = CycleStateMachine()
        assert sm.can_advance(CyclePhase.ANALYSIS, [CycleEvent("finding_added")]) is True

    def test_returns_false_when_no_completion_event(self) -> None:
        sm = CycleStateMachine()
        assert sm.can_advance(CyclePhase.ANALYSIS, [CycleEvent("irrelevant_event")]) is False

    def test_returns_false_for_empty_event_list(self) -> None:
        sm = CycleStateMachine()
        assert sm.can_advance(CyclePhase.ANALYSIS, []) is False

    def test_returns_false_for_terminal_phase_regardless_of_events(self) -> None:
        """NEXT_CYCLE is terminal — no event can advance it."""
        sm = CycleStateMachine()
        assert sm.can_advance(CyclePhase.NEXT_CYCLE, [CycleEvent("anything")]) is False
        assert sm.can_advance(CyclePhase.NEXT_CYCLE, []) is False

    def test_each_phase_has_a_distinct_completion_event(self) -> None:
        """Every non-terminal phase advances on its own completion event."""
        sm = CycleStateMachine()
        cases = [
            (CyclePhase.ANALYSIS, "finding_added"),
            (CyclePhase.SYNTHESIS, "proposal_added"),
            (CyclePhase.GATE, "proposal_approved"),
            (CyclePhase.EXECUTION, "execution_completed"),
            (CyclePhase.VERIFICATION, "verification_passed"),
        ]
        for phase, event_type in cases:
            assert sm.can_advance(phase, [CycleEvent(event_type)]) is True

    def test_completion_event_for_wrong_phase_does_not_advance(self) -> None:
        """finding_added completes ANALYSIS but must not advance SYNTHESIS."""
        sm = CycleStateMachine()
        assert sm.can_advance(CyclePhase.SYNTHESIS, [CycleEvent("finding_added")]) is False

    def test_extra_events_do_not_block_completion(self) -> None:
        """Unrelated events mixed in do not prevent phase completion."""
        sm = CycleStateMachine()
        events = [
            CycleEvent("noise"),
            CycleEvent("finding_added"),
            CycleEvent("more_noise"),
        ]
        assert sm.can_advance(CyclePhase.ANALYSIS, events) is True

    def test_event_metadata_is_ignored_for_completion(self) -> None:
        """Metadata on events does not affect completion logic."""
        sm = CycleStateMachine()
        event = CycleEvent("finding_added", metadata={"agent": "repo-audit", "cost": 0.1})
        assert sm.can_advance(CyclePhase.ANALYSIS, [event]) is True


class TestNextPhase:
    """Tests for CycleStateMachine.next_phase."""

    def test_analysis_advances_to_synthesis(self) -> None:
        assert CycleStateMachine().next_phase(CyclePhase.ANALYSIS) == CyclePhase.SYNTHESIS

    def test_full_linear_progression(self) -> None:
        sm = CycleStateMachine()
        expected_pairs = [
            (CyclePhase.ANALYSIS, CyclePhase.SYNTHESIS),
            (CyclePhase.SYNTHESIS, CyclePhase.GATE),
            (CyclePhase.GATE, CyclePhase.EXECUTION),
            (CyclePhase.EXECUTION, CyclePhase.VERIFICATION),
            (CyclePhase.VERIFICATION, CyclePhase.NEXT_CYCLE),
        ]
        for current, expected_next in expected_pairs:
            assert sm.next_phase(current) == expected_next

    def test_terminal_phase_returns_none(self) -> None:
        assert CycleStateMachine().next_phase(CyclePhase.NEXT_CYCLE) is None


class TestCurrentPhaseFromBead:
    """Tests for CycleStateMachine.current_phase_from_bead."""

    def test_returns_matching_phase_for_all_valid_values(self) -> None:
        sm = CycleStateMachine()
        for phase in CyclePhase:
            bead = _bead(phase.value)
            assert sm.current_phase_from_bead(bead) == phase

    def test_raises_value_error_for_unknown_phase_string(self) -> None:
        sm = CycleStateMachine()
        # model_construct bypasses Pydantic validation so we can inject an
        # invalid phase value — exactly the scenario current_phase_from_bead guards against.
        bead = CycleBead.model_construct(cycle_id="test-cycle", repo="owner/repo", phase="bogus_phase")
        with pytest.raises(ValueError, match="Unknown phase value"):
            sm.current_phase_from_bead(bead)

    def test_error_message_includes_cycle_id(self) -> None:
        sm = CycleStateMachine()
        bead = CycleBead.model_construct(cycle_id="my-cycle-99", repo="r/r", phase="bad")
        with pytest.raises(ValueError, match="my-cycle-99"):
            sm.current_phase_from_bead(bead)


class TestAdvance:
    """Tests for CycleStateMachine.advance."""

    def test_advances_from_analysis_with_finding_added(self) -> None:
        sm = CycleStateMachine()
        bead = _bead("analysis")
        result = sm.advance(bead, [CycleEvent("finding_added")])
        assert result == CyclePhase.SYNTHESIS

    def test_full_phase_sequence_via_advance(self) -> None:
        sm = CycleStateMachine()
        transitions = [
            ("analysis", "finding_added", CyclePhase.SYNTHESIS),
            ("synthesis", "proposal_added", CyclePhase.GATE),
            ("gate", "proposal_approved", CyclePhase.EXECUTION),
            ("execution", "execution_completed", CyclePhase.VERIFICATION),
            ("verification", "verification_passed", CyclePhase.NEXT_CYCLE),
        ]
        for phase_val, event_type, expected in transitions:
            bead = _bead(phase_val)
            assert sm.advance(bead, [CycleEvent(event_type)]) == expected

    def test_raises_when_no_completion_event(self) -> None:
        sm = CycleStateMachine()
        bead = _bead("analysis")
        with pytest.raises(InvalidPhaseTransitionError, match="not complete"):
            sm.advance(bead, [])

    def test_raises_when_wrong_completion_event(self) -> None:
        sm = CycleStateMachine()
        bead = _bead("synthesis")
        # finding_added only completes ANALYSIS
        with pytest.raises(InvalidPhaseTransitionError, match="not complete"):
            sm.advance(bead, [CycleEvent("finding_added")])

    def test_raises_for_terminal_phase(self) -> None:
        """NEXT_CYCLE cannot be advanced even with any events."""
        sm = CycleStateMachine()
        bead = _bead("complete")
        with pytest.raises(InvalidPhaseTransitionError):
            sm.advance(bead, [CycleEvent("verification_passed")])

    def test_does_not_mutate_bead(self) -> None:
        """advance() is pure — the input bead's phase is unchanged."""
        sm = CycleStateMachine()
        bead = _bead("analysis")
        sm.advance(bead, [CycleEvent("finding_added")])
        assert bead.phase == "analysis"

    def test_event_metadata_does_not_block_transition(self) -> None:
        sm = CycleStateMachine()
        bead = _bead("analysis")
        event = CycleEvent("finding_added", metadata={"issue": 42, "cost_usd": 0.07})
        assert sm.advance(bead, [event]) == CyclePhase.SYNTHESIS
