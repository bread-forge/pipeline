"""Tests for AgentDispatcher and related dispatch module."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from beads.store import BeadStore
from beads.types import CycleBead, FindingBead

from pipeline.cycle.phase import CyclePhase
from pipeline.cycle.state_machine import InvalidPhaseTransitionError
from pipeline.dispatch import AgentDispatcher, AgentDispatchError
from pipeline.events.log import EventLog
from pipeline.events.types import AgentCompleted, AgentDispatched

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _store(tmp_path: Path) -> BeadStore:
    return BeadStore(tmp_path, "owner/repo")


def _event_log(tmp_path: Path) -> EventLog:
    return EventLog("owner", "repo", "cycle-1", base_dir=tmp_path)


def _bead(phase: str = "analysis") -> CycleBead:
    return CycleBead(cycle_id="cycle-1", repo="owner/repo", phase=phase)


def _finding(
    finding_id: str = "f1",
    cycle_id: str = "cycle-1",
    repo: str = "owner/repo",
) -> FindingBead:
    return FindingBead(
        id=finding_id,
        agent="depth",
        timestamp=datetime.now(UTC),
        staleness_class="structural",
        confidence=0.8,
        reasoning="Some reasoning",
        severity="high",
        repo=repo,
        cycle_id=cycle_id,
    )


def _dispatcher(
    tmp_path: Path,
    store: BeadStore | None = None,
    event_log: EventLog | None = None,
) -> AgentDispatcher:
    st = store or _store(tmp_path)
    el = event_log or _event_log(tmp_path)
    return AgentDispatcher(
        cycle_id="cycle-1",
        repo="owner/repo",
        store=st,
        event_log=el,
    )


# ---------------------------------------------------------------------------
# Tests: AgentDispatcher.__init__
# ---------------------------------------------------------------------------


class TestAgentDispatcherInit:
    """Tests for AgentDispatcher construction."""

    def test_accepts_injected_state_machine(self, tmp_path: Path) -> None:
        """Custom state_machine is stored and used instead of the default."""
        sm = MagicMock()
        d = AgentDispatcher(
            cycle_id="c1",
            repo="owner/repo",
            store=_store(tmp_path),
            event_log=_event_log(tmp_path),
            state_machine=sm,
        )
        assert d._sm is sm

    def test_creates_default_state_machine_when_none_given(self, tmp_path: Path) -> None:
        from pipeline.cycle.state_machine import CycleStateMachine

        d = _dispatcher(tmp_path)
        assert isinstance(d._sm, CycleStateMachine)


# ---------------------------------------------------------------------------
# Tests: AgentDispatcher.dispatch — subprocess interactions
# ---------------------------------------------------------------------------


class TestDispatchSubprocessCalls:
    """Verify subprocess.run is called correctly for each agent."""

    def test_runs_repo_audit_for_each_agent(self, tmp_path: Path) -> None:
        """Each agent name triggers one subprocess.run call."""
        d = _dispatcher(tmp_path)
        bead = _bead()

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="")
            d.dispatch(["depth", "coverage"], Path("/repo"), bead)

        assert mock_run.call_count == 2

    def test_subprocess_command_is_repo_audit_run_with_repo_path(self, tmp_path: Path) -> None:
        d = _dispatcher(tmp_path)
        bead = _bead()

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="")
            d.dispatch(["depth"], Path("/some/repo"), bead)

        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert cmd == ["repo-audit", "run", "/some/repo"]

    def test_agent_name_passed_via_env_var(self, tmp_path: Path) -> None:
        """REPO_AUDIT_AGENT env var is set to the agent name for each call."""
        d = _dispatcher(tmp_path)
        bead = _bead()

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="")
            d.dispatch(["my-agent"], Path("/repo"), bead)

        _, kwargs = mock_run.call_args
        assert kwargs["env"]["REPO_AUDIT_AGENT"] == "my-agent"

    def test_agents_run_in_order(self, tmp_path: Path) -> None:
        """Agents are dispatched sequentially in the provided order."""
        d = _dispatcher(tmp_path)
        bead = _bead()
        order: list[str] = []

        def fake_run(cmd: list[str], **_kwargs: object) -> Mock:
            env = _kwargs.get("env", {})
            order.append(str(env.get("REPO_AUDIT_AGENT", "")))
            return Mock(returncode=0, stderr="")

        with patch("pipeline.dispatch.agent.subprocess.run", side_effect=fake_run):
            d.dispatch(["alpha", "beta", "gamma"], Path("/repo"), bead)

        assert order == ["alpha", "beta", "gamma"]

    def test_empty_agent_list_skips_subprocess_and_still_transitions(self, tmp_path: Path) -> None:
        """Zero agents: no subprocess calls; state machine still advances."""
        d = _dispatcher(tmp_path)
        bead = _bead()

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            d.dispatch([], Path("/repo"), bead)

        mock_run.assert_not_called()
        assert bead.phase == CyclePhase.SYNTHESIS.value


# ---------------------------------------------------------------------------
# Tests: AgentDispatcher.dispatch — event emission
# ---------------------------------------------------------------------------


class TestDispatchEventEmission:
    """Verify AgentDispatched and AgentCompleted events are written to the log."""

    def test_emits_agent_dispatched_before_subprocess(self, tmp_path: Path) -> None:
        """AgentDispatched appears before AgentCompleted in the log."""
        d = _dispatcher(tmp_path)
        el = d._event_log

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="")
            d.dispatch(["depth"], Path("/repo"), _bead())

        events = el.replay()
        assert isinstance(events[0], AgentDispatched)
        assert isinstance(events[1], AgentCompleted)

    def test_emits_dispatched_and_completed_for_each_agent(self, tmp_path: Path) -> None:
        """Two agents → two AgentDispatched and two AgentCompleted events."""
        d = _dispatcher(tmp_path)
        el = d._event_log

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="")
            d.dispatch(["a", "b"], Path("/repo"), _bead())

        events = el.replay()
        dispatched = [e for e in events if isinstance(e, AgentDispatched)]
        completed = [e for e in events if isinstance(e, AgentCompleted)]
        assert len(dispatched) == 2
        assert len(completed) == 2

    def test_agent_dispatched_has_correct_cycle_id(self, tmp_path: Path) -> None:
        d = _dispatcher(tmp_path)
        el = d._event_log

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="")
            d.dispatch(["depth"], Path("/repo"), _bead())

        dispatched = [e for e in el.replay() if isinstance(e, AgentDispatched)][0]
        assert dispatched.cycle_id == "cycle-1"

    def test_agent_dispatched_branch_matches_agent_name(self, tmp_path: Path) -> None:
        """The branch field on AgentDispatched carries the agent name."""
        d = _dispatcher(tmp_path)
        el = d._event_log

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="")
            d.dispatch(["my-auditor"], Path("/repo"), _bead())

        dispatched = [e for e in el.replay() if isinstance(e, AgentDispatched)][0]
        assert dispatched.branch == "my-auditor"

    def test_agent_completed_success_true_on_zero_exit(self, tmp_path: Path) -> None:
        d = _dispatcher(tmp_path)
        el = d._event_log

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="")
            d.dispatch(["depth"], Path("/repo"), _bead())

        completed = [e for e in el.replay() if isinstance(e, AgentCompleted)][0]
        assert completed.success is True

    def test_agent_completed_success_false_on_nonzero_exit(self, tmp_path: Path) -> None:
        """success=False is emitted before AgentDispatchError is raised."""
        d = _dispatcher(tmp_path)
        el = d._event_log

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1, stderr="boom")
            with pytest.raises(AgentDispatchError):
                d.dispatch(["depth"], Path("/repo"), _bead())

        completed = [e for e in el.replay() if isinstance(e, AgentCompleted)][0]
        assert completed.success is False

    def test_event_order_dispatched_then_completed_per_agent(self, tmp_path: Path) -> None:
        """For two agents, the full interleaved order is D1 C1 D2 C2."""
        d = _dispatcher(tmp_path)
        el = d._event_log

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="")
            d.dispatch(["a", "b"], Path("/repo"), _bead())

        event_types = [type(e).__name__ for e in el.replay()]
        assert event_types == [
            "AgentDispatched",
            "AgentCompleted",
            "AgentDispatched",
            "AgentCompleted",
        ]


# ---------------------------------------------------------------------------
# Tests: AgentDispatcher.dispatch — error handling
# ---------------------------------------------------------------------------


class TestDispatchErrors:
    """Verify AgentDispatchError is raised on subprocess failure."""

    def test_raises_agent_dispatch_error_on_nonzero_exit(self, tmp_path: Path) -> None:
        d = _dispatcher(tmp_path)

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=2, stderr="fatal error")
            with pytest.raises(AgentDispatchError, match="exit.*code 2"):
                d.dispatch(["depth"], Path("/repo"), _bead())

    def test_error_message_includes_agent_name(self, tmp_path: Path) -> None:
        d = _dispatcher(tmp_path)

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1, stderr="")
            with pytest.raises(AgentDispatchError, match="failing-agent"):
                d.dispatch(["failing-agent"], Path("/repo"), _bead())

    def test_subsequent_agents_not_run_after_failure(self, tmp_path: Path) -> None:
        """Dispatch aborts on the first failing agent."""
        d = _dispatcher(tmp_path)
        calls: list[str] = []

        def fake_run(cmd: list[str], **kwargs: object) -> Mock:
            env = kwargs.get("env", {})
            agent = str(env.get("REPO_AUDIT_AGENT", ""))
            calls.append(agent)
            code = 1 if agent == "bad" else 0
            return Mock(returncode=code, stderr="")

        with (
            patch("pipeline.dispatch.agent.subprocess.run", side_effect=fake_run),
            pytest.raises(AgentDispatchError),
        ):
            d.dispatch(["bad", "never-runs"], Path("/repo"), _bead())

        assert calls == ["bad"]
        assert "never-runs" not in calls

    def test_bead_phase_not_updated_on_failure(self, tmp_path: Path) -> None:
        """A failed agent leaves the bead in the original phase."""
        d = _dispatcher(tmp_path)
        bead = _bead("analysis")

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1, stderr="")
            with pytest.raises(AgentDispatchError):
                d.dispatch(["bad"], Path("/repo"), bead)

        assert bead.phase == "analysis"


# ---------------------------------------------------------------------------
# Tests: AgentDispatcher.dispatch — findings and phase transition
# ---------------------------------------------------------------------------


class TestDispatchFindingsAndPhaseTransition:
    """Verify findings collection and ANALYSIS → SYNTHESIS transition."""

    def test_returns_findings_for_current_cycle(self, tmp_path: Path) -> None:
        """Findings written to the store by agents are returned."""
        store = _store(tmp_path)
        finding = _finding(finding_id="f1", cycle_id="cycle-1")
        store.write_finding(finding)

        d = _dispatcher(tmp_path, store=store)
        bead = _bead()

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="")
            result = d.dispatch(["depth"], Path("/repo"), bead)

        assert len(result) == 1
        assert result[0].id == "f1"

    def test_excludes_findings_from_other_cycles(self, tmp_path: Path) -> None:
        """Findings with a different cycle_id are not returned."""
        store = _store(tmp_path)
        store.write_finding(_finding(finding_id="mine", cycle_id="cycle-1"))
        store.write_finding(_finding(finding_id="other", cycle_id="cycle-99"))

        d = _dispatcher(tmp_path, store=store)

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="")
            result = d.dispatch(["depth"], Path("/repo"), _bead())

        ids = {f.id for f in result}
        assert ids == {"mine"}

    def test_transitions_bead_to_synthesis_after_agents_complete(self, tmp_path: Path) -> None:
        """Bead phase is updated to synthesis when all agents succeed."""
        d = _dispatcher(tmp_path)
        bead = _bead("analysis")

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="")
            d.dispatch(["depth"], Path("/repo"), bead)

        assert bead.phase == CyclePhase.SYNTHESIS.value

    def test_bead_persisted_to_store_after_transition(self, tmp_path: Path) -> None:
        """Updated bead is written to the store."""
        store = _store(tmp_path)
        bead = _bead("analysis")
        store.write_cycle(bead)

        d = _dispatcher(tmp_path, store=store)

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="")
            d.dispatch(["depth"], Path("/repo"), bead)

        on_disk = store.read_cycle("cycle-1")
        assert on_disk is not None
        assert on_disk.phase == CyclePhase.SYNTHESIS.value

    def test_transitions_even_with_no_findings(self, tmp_path: Path) -> None:
        """Zero findings still advance the cycle via all_agents_completed."""
        d = _dispatcher(tmp_path)
        bead = _bead("analysis")

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="")
            result = d.dispatch(["depth"], Path("/repo"), bead)

        assert result == []
        assert bead.phase == CyclePhase.SYNTHESIS.value

    def test_raises_when_bead_not_in_analysis_phase(self, tmp_path: Path) -> None:
        """Dispatching when the bead is not in ANALYSIS raises an error."""
        d = _dispatcher(tmp_path)
        bead = _bead("synthesis")

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="")
            with pytest.raises(InvalidPhaseTransitionError):
                d.dispatch(["depth"], Path("/repo"), bead)

    def test_returns_empty_list_when_no_agents(self, tmp_path: Path) -> None:
        d = _dispatcher(tmp_path)
        bead = _bead("analysis")

        with patch("pipeline.dispatch.agent.subprocess.run"):
            result = d.dispatch([], Path("/repo"), bead)

        assert result == []

    def test_multiple_findings_all_returned(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        for i in range(3):
            store.write_finding(_finding(finding_id=f"f{i}", cycle_id="cycle-1"))

        d = _dispatcher(tmp_path, store=store)

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="")
            result = d.dispatch(["depth"], Path("/repo"), _bead())

        assert len(result) == 3


# ---------------------------------------------------------------------------
# Tests: state_machine.py — all_agents_completed trigger
# ---------------------------------------------------------------------------


class TestStateMachineAllAgentsCompleted:
    """Verify the new all_agents_completed trigger in CycleStateMachine."""

    def test_analysis_advances_on_all_agents_completed(self) -> None:
        from pipeline.cycle.state_machine import CycleEvent, CycleStateMachine

        sm = CycleStateMachine()
        assert sm.can_advance(CyclePhase.ANALYSIS, [CycleEvent("all_agents_completed")]) is True

    def test_all_agents_completed_does_not_advance_synthesis(self) -> None:
        """The new trigger is specific to ANALYSIS, not other phases."""
        from pipeline.cycle.state_machine import CycleEvent, CycleStateMachine

        sm = CycleStateMachine()
        assert sm.can_advance(CyclePhase.SYNTHESIS, [CycleEvent("all_agents_completed")]) is False

    def test_finding_added_still_advances_analysis(self) -> None:
        """Original trigger is preserved."""
        from pipeline.cycle.state_machine import CycleEvent, CycleStateMachine

        sm = CycleStateMachine()
        assert sm.can_advance(CyclePhase.ANALYSIS, [CycleEvent("finding_added")]) is True

    def test_advance_returns_synthesis_from_analysis_with_new_trigger(self) -> None:
        from pipeline.cycle.state_machine import CycleEvent, CycleStateMachine

        sm = CycleStateMachine()
        bead = CycleBead(cycle_id="c", repo="o/r", phase="analysis")
        result = sm.advance(bead, [CycleEvent("all_agents_completed")])
        assert result == CyclePhase.SYNTHESIS
