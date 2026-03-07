"""Tests for GateActions — ProposalBead state transitions and GateDecision events."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from beads.types import ProposalBead

from pipeline.events.log import EventLog
from pipeline.events.types import GateDecision
from pipeline.gate.actions import GateActions


def _make_proposal(
    proposal_id: str = "prop-1",
    cycle_id: str = "cycle-1",
    status: str = "pending",
) -> ProposalBead:
    return ProposalBead(
        proposal_id=proposal_id,
        cycle_id=cycle_id,
        repo="owner/repo",
        spec_hash="abc123",
        spec_path="/tmp/spec.json",
        status=status,
    )


def _make_store(proposal: ProposalBead | None) -> Mock:
    store = Mock()
    store.read_proposal.return_value = proposal
    return store


class TestGateActionsApprove:
    """Tests for GateActions.approve()."""

    def test_sets_status_to_approved(self) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        actions = GateActions(store)

        actions.approve("prop-1", review_seconds=10.0)

        written = store.write_proposal.call_args[0][0]
        assert written.status == "approved"

    def test_stamps_gate_decision_at(self) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        before = datetime.now(UTC)
        actions = GateActions(store)

        actions.approve("prop-1", review_seconds=None)

        written = store.write_proposal.call_args[0][0]
        assert written.gate_decision_at is not None
        assert written.gate_decision_at >= before

    def test_records_review_seconds(self) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        actions = GateActions(store)

        actions.approve("prop-1", review_seconds=42.5)

        written = store.write_proposal.call_args[0][0]
        assert written.review_seconds == pytest.approx(42.5)

    def test_review_seconds_none_is_stored(self) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        actions = GateActions(store)

        actions.approve("prop-1", review_seconds=None)

        written = store.write_proposal.call_args[0][0]
        assert written.review_seconds is None

    def test_emits_gate_decision_event_approved_true(self, tmp_path: Path) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        event_log = EventLog("owner", "repo", "cycle-1", base_dir=tmp_path)
        actions = GateActions(store, event_log)

        actions.approve("prop-1", review_seconds=5.0)

        events = event_log.replay()
        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, GateDecision)
        assert evt.approved is True
        assert evt.cycle_id == "cycle-1"
        assert evt.reason == ""

    def test_event_timestamp_is_after_call_start(self, tmp_path: Path) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        event_log = EventLog("owner", "repo", "cycle-1", base_dir=tmp_path)
        before = datetime.now(UTC)
        actions = GateActions(store, event_log)

        actions.approve("prop-1", review_seconds=None)

        evt = event_log.replay()[0]
        assert evt.timestamp >= before  # type: ignore[union-attr]

    def test_no_event_emitted_when_event_log_is_none(self) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        actions = GateActions(store, event_log=None)

        # Should not raise even with no event log
        actions.approve("prop-1", review_seconds=1.0)

        store.write_proposal.assert_called_once()

    def test_raises_key_error_when_proposal_not_found(self) -> None:
        store = _make_store(proposal=None)
        actions = GateActions(store)

        with pytest.raises(KeyError, match="prop-missing"):
            actions.approve("prop-missing", review_seconds=None)

    def test_loads_proposal_by_id(self) -> None:
        proposal = _make_proposal(proposal_id="prop-abc")
        store = _make_store(proposal)
        actions = GateActions(store)

        actions.approve("prop-abc", review_seconds=None)

        store.read_proposal.assert_called_once_with("prop-abc")

    def test_writes_proposal_exactly_once(self) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        actions = GateActions(store)

        actions.approve("prop-1", review_seconds=None)

        store.write_proposal.assert_called_once()


class TestGateActionsReject:
    """Tests for GateActions.reject()."""

    def test_sets_status_to_rejected(self) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        actions = GateActions(store)

        actions.reject("prop-1", reason="Not ready", review_seconds=None)

        written = store.write_proposal.call_args[0][0]
        assert written.status == "rejected"

    def test_stamps_gate_decision_at(self) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        before = datetime.now(UTC)
        actions = GateActions(store)

        actions.reject("prop-1", reason="Too risky", review_seconds=None)

        written = store.write_proposal.call_args[0][0]
        assert written.gate_decision_at is not None
        assert written.gate_decision_at >= before

    def test_records_review_seconds(self) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        actions = GateActions(store)

        actions.reject("prop-1", reason="Reason", review_seconds=7.2)

        written = store.write_proposal.call_args[0][0]
        assert written.review_seconds == pytest.approx(7.2)

    def test_emits_gate_decision_event_approved_false(self, tmp_path: Path) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        event_log = EventLog("owner", "repo", "cycle-1", base_dir=tmp_path)
        actions = GateActions(store, event_log)

        actions.reject("prop-1", reason="Bad idea", review_seconds=3.0)

        events = event_log.replay()
        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, GateDecision)
        assert evt.approved is False
        assert evt.reason == "Bad idea"
        assert evt.cycle_id == "cycle-1"

    def test_event_carries_rejection_reason(self, tmp_path: Path) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        event_log = EventLog("owner", "repo", "cycle-1", base_dir=tmp_path)
        actions = GateActions(store, event_log)

        actions.reject("prop-1", reason="Scope too large", review_seconds=None)

        evt = event_log.replay()[0]
        assert isinstance(evt, GateDecision)
        assert evt.reason == "Scope too large"

    def test_no_event_emitted_when_event_log_is_none(self) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        actions = GateActions(store, event_log=None)

        actions.reject("prop-1", reason="x", review_seconds=None)

        store.write_proposal.assert_called_once()

    def test_raises_key_error_when_proposal_not_found(self) -> None:
        store = _make_store(proposal=None)
        actions = GateActions(store)

        with pytest.raises(KeyError):
            actions.reject("missing", reason="x", review_seconds=None)

    def test_loads_proposal_by_id(self) -> None:
        proposal = _make_proposal(proposal_id="prop-rej")
        store = _make_store(proposal)
        actions = GateActions(store)

        actions.reject("prop-rej", reason="nope", review_seconds=None)

        store.read_proposal.assert_called_once_with("prop-rej")


class TestGateActionsDefer:
    """Tests for GateActions.defer()."""

    def test_sets_status_to_deferred(self) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        defer_to = datetime(2025, 6, 1, tzinfo=UTC)
        actions = GateActions(store)

        actions.defer("prop-1", defer_until=defer_to, review_seconds=None)

        written = store.write_proposal.call_args[0][0]
        assert written.status == "deferred"

    def test_stamps_gate_decision_at(self) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        before = datetime.now(UTC)
        defer_to = datetime(2025, 6, 1, tzinfo=UTC)
        actions = GateActions(store)

        actions.defer("prop-1", defer_until=defer_to, review_seconds=None)

        written = store.write_proposal.call_args[0][0]
        assert written.gate_decision_at is not None
        assert written.gate_decision_at >= before

    def test_records_review_seconds(self) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        defer_to = datetime(2025, 6, 1, tzinfo=UTC)
        actions = GateActions(store)

        actions.defer("prop-1", defer_until=defer_to, review_seconds=20.0)

        written = store.write_proposal.call_args[0][0]
        assert written.review_seconds == pytest.approx(20.0)

    def test_emits_gate_decision_approved_false(self, tmp_path: Path) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        event_log = EventLog("owner", "repo", "cycle-1", base_dir=tmp_path)
        defer_to = datetime(2025, 6, 1, tzinfo=UTC)
        actions = GateActions(store, event_log)

        actions.defer("prop-1", defer_until=defer_to, review_seconds=None)

        events = event_log.replay()
        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, GateDecision)
        assert evt.approved is False
        assert evt.cycle_id == "cycle-1"

    def test_event_reason_encodes_defer_until_date(self, tmp_path: Path) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        event_log = EventLog("owner", "repo", "cycle-1", base_dir=tmp_path)
        defer_to = datetime(2025, 6, 1, tzinfo=UTC)
        actions = GateActions(store, event_log)

        actions.defer("prop-1", defer_until=defer_to, review_seconds=None)

        evt = event_log.replay()[0]
        assert isinstance(evt, GateDecision)
        # Reason must encode the defer-until timestamp
        assert "2025-06-01" in evt.reason

    def test_no_event_emitted_when_event_log_is_none(self) -> None:
        proposal = _make_proposal()
        store = _make_store(proposal)
        defer_to = datetime(2025, 6, 1, tzinfo=UTC)
        actions = GateActions(store, event_log=None)

        actions.defer("prop-1", defer_until=defer_to, review_seconds=None)

        store.write_proposal.assert_called_once()

    def test_raises_key_error_when_proposal_not_found(self) -> None:
        store = _make_store(proposal=None)
        defer_to = datetime(2025, 6, 1, tzinfo=UTC)
        actions = GateActions(store)

        with pytest.raises(KeyError):
            actions.defer("missing", defer_until=defer_to, review_seconds=None)

    def test_loads_proposal_by_id(self) -> None:
        proposal = _make_proposal(proposal_id="prop-def")
        store = _make_store(proposal)
        defer_to = datetime(2025, 6, 1, tzinfo=UTC)
        actions = GateActions(store)

        actions.defer("prop-def", defer_until=defer_to, review_seconds=None)

        store.read_proposal.assert_called_once_with("prop-def")
