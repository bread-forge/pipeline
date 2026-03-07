"""Integration tests for AgentDispatcher — subprocess dispatch, event emission,
and ANALYSIS → SYNTHESIS state transition."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from beads.store import BeadStore
from beads.types import CycleBead, FindingBead

from pipeline.cycle.phase import CyclePhase
from pipeline.cycle.state_machine import InvalidPhaseTransitionError
from pipeline.dispatch import AgentDispatcher, AgentDispatchError
from pipeline.events.log import EventLog
from pipeline.events.types import AgentCompleted, AgentDispatched

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

CYCLE_ID = "integ-cycle-1"
REPO = "owner/repo"


def _make_store(tmp_path: Path) -> BeadStore:
    return BeadStore(tmp_path, REPO)


def _make_event_log(tmp_path: Path, cycle_id: str = CYCLE_ID) -> EventLog:
    return EventLog("owner", "repo", cycle_id, base_dir=tmp_path)


def _make_bead(phase: str = "analysis", cycle_id: str = CYCLE_ID) -> CycleBead:
    return CycleBead(cycle_id=cycle_id, repo=REPO, phase=phase)


def _make_finding(
    finding_id: str,
    cycle_id: str = CYCLE_ID,
    repo: str = REPO,
) -> FindingBead:
    return FindingBead(
        id=finding_id,
        agent="auditor",
        timestamp=datetime.now(UTC),
        staleness_class="structural",
        confidence=0.9,
        reasoning="Integration test finding",
        severity="high",
        repo=repo,
        cycle_id=cycle_id,
    )


def _make_dispatcher(
    tmp_path: Path,
    store: BeadStore | None = None,
    event_log: EventLog | None = None,
    cycle_id: str = CYCLE_ID,
) -> AgentDispatcher:
    return AgentDispatcher(
        cycle_id=cycle_id,
        repo=REPO,
        store=store or _make_store(tmp_path),
        event_log=event_log or _make_event_log(tmp_path, cycle_id),
    )


def _success_run(*_args: object, **_kwargs: object) -> Mock:
    return Mock(returncode=0, stderr="")


# ---------------------------------------------------------------------------
# Subprocess dispatch
# ---------------------------------------------------------------------------


class TestSubprocessDispatch:
    """Each configured agent is launched as a subprocess."""

    def test_single_agent_spawns_one_subprocess(self, tmp_path: Path) -> None:
        """One agent → exactly one subprocess.run call."""
        dispatcher = _make_dispatcher(tmp_path)
        bead = _make_bead()

        with patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_run) as mock_run:
            dispatcher.dispatch(["depth"], Path("/repo"), bead)

        assert mock_run.call_count == 1

    def test_two_agents_spawn_two_subprocesses(self, tmp_path: Path) -> None:
        dispatcher = _make_dispatcher(tmp_path)
        bead = _make_bead()

        with patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_run) as mock_run:
            dispatcher.dispatch(["depth", "coverage"], Path("/repo"), bead)

        assert mock_run.call_count == 2

    def test_subprocess_command_contains_repo_path(self, tmp_path: Path) -> None:
        """The repo path is forwarded as the third argument to repo-audit run."""
        dispatcher = _make_dispatcher(tmp_path)
        bead = _make_bead()
        repo_path = Path("/projects/my-repo")

        with patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_run) as mock_run:
            dispatcher.dispatch(["linter"], repo_path, bead)

        cmd = mock_run.call_args[0][0]
        assert cmd == ["repo-audit", "run", str(repo_path)]

    def test_agent_name_set_in_env(self, tmp_path: Path) -> None:
        """REPO_AUDIT_AGENT env var reflects the dispatched agent name."""
        dispatcher = _make_dispatcher(tmp_path)
        bead = _make_bead()

        with patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_run) as mock_run:
            dispatcher.dispatch(["my-auditor"], Path("/repo"), bead)

        env = mock_run.call_args[1]["env"]
        assert env["REPO_AUDIT_AGENT"] == "my-auditor"

    def test_agents_dispatched_sequentially(self, tmp_path: Path) -> None:
        """Agents run in the given order, not in parallel."""
        dispatcher = _make_dispatcher(tmp_path)
        bead = _make_bead()
        dispatch_order: list[str] = []

        def capture_order(cmd: list[str], **kwargs: object) -> Mock:
            env = kwargs.get("env", {})
            dispatch_order.append(str(env.get("REPO_AUDIT_AGENT", "")))
            return Mock(returncode=0, stderr="")

        with patch("pipeline.dispatch.agent.subprocess.run", side_effect=capture_order):
            dispatcher.dispatch(["first", "second", "third"], Path("/repo"), bead)

        assert dispatch_order == ["first", "second", "third"]

    def test_no_agents_skips_subprocess_entirely(self, tmp_path: Path) -> None:
        """Zero agents: subprocess.run is never called."""
        dispatcher = _make_dispatcher(tmp_path)
        bead = _make_bead()

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            dispatcher.dispatch([], Path("/repo"), bead)

        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------


class TestEventEmission:
    """AgentDispatched and AgentCompleted events are appended to the event log."""

    def test_dispatched_event_precedes_completed_for_one_agent(self, tmp_path: Path) -> None:
        """For a single agent, AgentDispatched appears before AgentCompleted."""
        event_log = _make_event_log(tmp_path)
        dispatcher = _make_dispatcher(tmp_path, event_log=event_log)

        with patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_run):
            dispatcher.dispatch(["depth"], Path("/repo"), _make_bead())

        events = event_log.replay()
        assert len(events) == 2
        assert isinstance(events[0], AgentDispatched)
        assert isinstance(events[1], AgentCompleted)

    def test_two_agents_produce_interleaved_events(self, tmp_path: Path) -> None:
        """Two agents → D1 C1 D2 C2 interleaving."""
        event_log = _make_event_log(tmp_path)
        dispatcher = _make_dispatcher(tmp_path, event_log=event_log)

        with patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_run):
            dispatcher.dispatch(["a", "b"], Path("/repo"), _make_bead())

        event_types = [type(e).__name__ for e in event_log.replay()]
        assert event_types == [
            "AgentDispatched",
            "AgentCompleted",
            "AgentDispatched",
            "AgentCompleted",
        ]

    def test_dispatched_event_carries_agent_name_as_branch(self, tmp_path: Path) -> None:
        """The branch field on AgentDispatched is the agent name."""
        event_log = _make_event_log(tmp_path)
        dispatcher = _make_dispatcher(tmp_path, event_log=event_log)

        with patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_run):
            dispatcher.dispatch(["my-agent"], Path("/repo"), _make_bead())

        dispatched = [e for e in event_log.replay() if isinstance(e, AgentDispatched)]
        assert dispatched[0].branch == "my-agent"

    def test_dispatched_event_carries_cycle_id(self, tmp_path: Path) -> None:
        event_log = _make_event_log(tmp_path)
        dispatcher = _make_dispatcher(tmp_path, event_log=event_log)

        with patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_run):
            dispatcher.dispatch(["depth"], Path("/repo"), _make_bead())

        dispatched = [e for e in event_log.replay() if isinstance(e, AgentDispatched)][0]
        assert dispatched.cycle_id == CYCLE_ID

    def test_completed_event_success_true_on_zero_exit(self, tmp_path: Path) -> None:
        event_log = _make_event_log(tmp_path)
        dispatcher = _make_dispatcher(tmp_path, event_log=event_log)

        with patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_run):
            dispatcher.dispatch(["depth"], Path("/repo"), _make_bead())

        completed = [e for e in event_log.replay() if isinstance(e, AgentCompleted)][0]
        assert completed.success is True

    def test_completed_event_success_false_on_nonzero_exit(self, tmp_path: Path) -> None:
        """success=False is emitted even when the agent fails."""
        event_log = _make_event_log(tmp_path)
        dispatcher = _make_dispatcher(tmp_path, event_log=event_log)

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1, stderr="crash")
            with pytest.raises(AgentDispatchError):
                dispatcher.dispatch(["bad-agent"], Path("/repo"), _make_bead())

        completed = [e for e in event_log.replay() if isinstance(e, AgentCompleted)][0]
        assert completed.success is False

    def test_no_events_emitted_when_agent_list_is_empty(self, tmp_path: Path) -> None:
        event_log = _make_event_log(tmp_path)
        dispatcher = _make_dispatcher(tmp_path, event_log=event_log)

        with patch("pipeline.dispatch.agent.subprocess.run"):
            dispatcher.dispatch([], Path("/repo"), _make_bead())

        events = event_log.replay()
        dispatched = [e for e in events if isinstance(e, AgentDispatched)]
        completed = [e for e in events if isinstance(e, AgentCompleted)]
        assert dispatched == []
        assert completed == []


# ---------------------------------------------------------------------------
# ANALYSIS → SYNTHESIS state transition
# ---------------------------------------------------------------------------


class TestPhaseTransition:
    """The cycle bead advances from ANALYSIS to SYNTHESIS after all agents run."""

    def test_bead_transitions_to_synthesis_on_success(self, tmp_path: Path) -> None:
        dispatcher = _make_dispatcher(tmp_path)
        bead = _make_bead("analysis")

        with patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_run):
            dispatcher.dispatch(["depth"], Path("/repo"), bead)

        assert bead.phase == CyclePhase.SYNTHESIS.value

    def test_bead_transitions_even_with_zero_agents(self, tmp_path: Path) -> None:
        """all_agents_completed trigger advances the phase even with no agents."""
        dispatcher = _make_dispatcher(tmp_path)
        bead = _make_bead("analysis")

        with patch("pipeline.dispatch.agent.subprocess.run"):
            dispatcher.dispatch([], Path("/repo"), bead)

        assert bead.phase == CyclePhase.SYNTHESIS.value

    def test_bead_persisted_to_store_after_transition(self, tmp_path: Path) -> None:
        """Updated bead is written to the store so the phase survives."""
        store = _make_store(tmp_path)
        bead = _make_bead("analysis")
        store.write_cycle(bead)

        dispatcher = _make_dispatcher(tmp_path, store=store)

        with patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_run):
            dispatcher.dispatch(["depth"], Path("/repo"), bead)

        on_disk = store.read_cycle(CYCLE_ID)
        assert on_disk is not None
        assert on_disk.phase == CyclePhase.SYNTHESIS.value

    def test_bead_phase_unchanged_when_agent_fails(self, tmp_path: Path) -> None:
        """A failing agent leaves the bead in ANALYSIS."""
        dispatcher = _make_dispatcher(tmp_path)
        bead = _make_bead("analysis")

        with patch("pipeline.dispatch.agent.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1, stderr="fail")
            with pytest.raises(AgentDispatchError):
                dispatcher.dispatch(["bad"], Path("/repo"), bead)

        assert bead.phase == "analysis"

    def test_raises_invalid_transition_when_bead_not_in_analysis(self, tmp_path: Path) -> None:
        """Dispatching when the bead is already in SYNTHESIS raises an error."""
        dispatcher = _make_dispatcher(tmp_path)
        bead = _make_bead("synthesis")

        with (
            patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_run),
            pytest.raises(InvalidPhaseTransitionError),
        ):
            dispatcher.dispatch(["depth"], Path("/repo"), bead)

    def test_subsequent_agents_not_run_after_failure(self, tmp_path: Path) -> None:
        """Dispatch stops at the first failed agent."""
        dispatcher = _make_dispatcher(tmp_path)
        called: list[str] = []

        def fake_run(cmd: list[str], **kwargs: object) -> Mock:
            env = kwargs.get("env", {})
            agent = str(env.get("REPO_AUDIT_AGENT", ""))
            called.append(agent)
            return Mock(returncode=1 if agent == "bad" else 0, stderr="")

        with (
            patch("pipeline.dispatch.agent.subprocess.run", side_effect=fake_run),
            pytest.raises(AgentDispatchError),
        ):
            dispatcher.dispatch(["bad", "never-runs"], Path("/repo"), _make_bead())

        assert called == ["bad"]
        assert "never-runs" not in called


# ---------------------------------------------------------------------------
# Findings collection
# ---------------------------------------------------------------------------


class TestFindingsCollection:
    """Findings from the store are returned after dispatch completes."""

    def test_returns_empty_list_when_no_findings(self, tmp_path: Path) -> None:
        dispatcher = _make_dispatcher(tmp_path)

        with patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_run):
            result = dispatcher.dispatch(["depth"], Path("/repo"), _make_bead())

        assert result == []

    def test_returns_findings_for_current_cycle(self, tmp_path: Path) -> None:
        """Findings written to the store before dispatch completes are returned."""
        store = _make_store(tmp_path)
        store.write_finding(_make_finding("f1"))

        dispatcher = _make_dispatcher(tmp_path, store=store)

        with patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_run):
            result = dispatcher.dispatch(["depth"], Path("/repo"), _make_bead())

        assert len(result) == 1
        assert result[0].id == "f1"

    def test_excludes_findings_from_other_cycles(self, tmp_path: Path) -> None:
        """Findings belonging to a different cycle_id are not returned."""
        store = _make_store(tmp_path)
        store.write_finding(_make_finding("mine", cycle_id=CYCLE_ID))
        store.write_finding(_make_finding("theirs", cycle_id="other-cycle"))

        dispatcher = _make_dispatcher(tmp_path, store=store)

        with patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_run):
            result = dispatcher.dispatch(["depth"], Path("/repo"), _make_bead())

        assert {f.id for f in result} == {"mine"}

    def test_returns_all_findings_for_current_cycle(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        for i in range(4):
            store.write_finding(_make_finding(f"f{i}"))

        dispatcher = _make_dispatcher(tmp_path, store=store)

        with patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_run):
            result = dispatcher.dispatch(["depth"], Path("/repo"), _make_bead())

        assert len(result) == 4
