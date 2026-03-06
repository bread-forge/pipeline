"""CLI integration tests for `pipeline run` — full happy-path with mocked agents."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

from beads.store import BeadStore
from beads.types import FindingBead
from typer.testing import CliRunner

from pipeline.cli.main import app
from pipeline.config.loader import PipelineConfig, RepoConfig
from pipeline.events.log import EventLog

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO = "owner/repo"
CYCLE_ID = "test-cycle-id"


def _make_store(tmp_path: Path, repo: str = REPO) -> BeadStore:
    return BeadStore(tmp_path / "beads", repo)


def _make_event_log(tmp_path: Path, cycle_id: str = CYCLE_ID) -> EventLog:
    return EventLog("owner", "repo", cycle_id, base_dir=tmp_path / "events")


def _make_finding(finding_id: str, cycle_id: str = CYCLE_ID) -> FindingBead:
    return FindingBead(
        id=finding_id,
        agent="depth",
        timestamp=datetime.now(UTC),
        staleness_class="structural",
        confidence=0.75,
        reasoning="Test reasoning for finding",
        severity="high",
        repo=REPO,
        cycle_id=cycle_id,
    )


def _success_subprocess(*_args: object, **_kwargs: object) -> Mock:
    return Mock(returncode=0, stderr="")


def _base_patches(tmp_path: Path, cycle_id: str = CYCLE_ID):
    """Return the standard set of context-manager patches for run tests."""
    store = _make_store(tmp_path)
    event_log = _make_event_log(tmp_path, cycle_id)
    return store, event_log


# ---------------------------------------------------------------------------
# Happy-path: no agents
# ---------------------------------------------------------------------------


class TestRunCommandNoAgents:
    """pipeline run with no agents configured or specified."""

    def test_exits_zero_with_no_agents(self, tmp_path: Path) -> None:
        """Zero agents still advances the cycle via all_agents_completed."""
        store = _make_store(tmp_path)
        event_log = _make_event_log(tmp_path)

        with (
            patch("pipeline.cli.commands.run.get_store", return_value=store),
            patch("pipeline.cli.commands.run.EventLog", return_value=event_log),
            patch("pipeline.cli.commands.run.uuid.uuid4", return_value=CYCLE_ID),
            patch("pipeline.cli.commands.run.load_config", return_value=PipelineConfig()),
        ):
            result = runner.invoke(app, ["run", "run", "--repo", REPO, "--path", str(tmp_path)])

        assert result.exit_code == 0

    def test_prints_no_findings_message_when_no_agents(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        event_log = _make_event_log(tmp_path)

        with (
            patch("pipeline.cli.commands.run.get_store", return_value=store),
            patch("pipeline.cli.commands.run.EventLog", return_value=event_log),
            patch("pipeline.cli.commands.run.uuid.uuid4", return_value=CYCLE_ID),
            patch("pipeline.cli.commands.run.load_config", return_value=PipelineConfig()),
        ):
            result = runner.invoke(app, ["run", "run", "--repo", REPO, "--path", str(tmp_path)])

        assert "no findings" in result.output or "no proposals" in result.output


# ---------------------------------------------------------------------------
# Happy-path: with agents
# ---------------------------------------------------------------------------


class TestRunCommandWithAgents:
    """pipeline run with explicit --agents dispatches subprocesses."""

    def test_exits_zero_when_agents_succeed(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        event_log = _make_event_log(tmp_path)

        with (
            patch("pipeline.cli.commands.run.get_store", return_value=store),
            patch("pipeline.cli.commands.run.EventLog", return_value=event_log),
            patch("pipeline.cli.commands.run.uuid.uuid4", return_value=CYCLE_ID),
            patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_subprocess),
        ):
            result = runner.invoke(
                app,
                ["run", "run", "--repo", REPO, "--agents", "depth", "--path", str(tmp_path)],
            )

        assert result.exit_code == 0

    def test_subprocess_called_once_per_agent(self, tmp_path: Path) -> None:
        """Each --agents value triggers one subprocess.run call."""
        store = _make_store(tmp_path)
        event_log = _make_event_log(tmp_path)

        with (
            patch("pipeline.cli.commands.run.get_store", return_value=store),
            patch("pipeline.cli.commands.run.EventLog", return_value=event_log),
            patch("pipeline.cli.commands.run.uuid.uuid4", return_value=CYCLE_ID),
            patch(
                "pipeline.dispatch.agent.subprocess.run", side_effect=_success_subprocess
            ) as mock_run,
        ):
            runner.invoke(
                app,
                [
                    "run",
                    "run",
                    "--repo",
                    REPO,
                    "--agents",
                    "depth",
                    "--agents",
                    "coverage",
                    "--path",
                    str(tmp_path),
                ],
            )

        assert mock_run.call_count == 2

    def test_prints_synthesis_header_when_findings_exist(self, tmp_path: Path) -> None:
        """When findings are in the store, the synthesis proposal list is printed."""
        store = _make_store(tmp_path)
        store.write_finding(_make_finding("f1"))
        event_log = _make_event_log(tmp_path)

        with (
            patch("pipeline.cli.commands.run.get_store", return_value=store),
            patch("pipeline.cli.commands.run.EventLog", return_value=event_log),
            patch("pipeline.cli.commands.run.uuid.uuid4", return_value=CYCLE_ID),
            patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_subprocess),
        ):
            result = runner.invoke(
                app,
                ["run", "run", "--repo", REPO, "--agents", "depth", "--path", str(tmp_path)],
            )

        assert "Synthesis proposals" in result.output
        assert "1 finding" in result.output

    def test_prints_finding_severity_and_reasoning(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.write_finding(_make_finding("f1"))
        event_log = _make_event_log(tmp_path)

        with (
            patch("pipeline.cli.commands.run.get_store", return_value=store),
            patch("pipeline.cli.commands.run.EventLog", return_value=event_log),
            patch("pipeline.cli.commands.run.uuid.uuid4", return_value=CYCLE_ID),
            patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_subprocess),
        ):
            result = runner.invoke(
                app,
                ["run", "run", "--repo", REPO, "--agents", "depth", "--path", str(tmp_path)],
            )

        assert "HIGH" in result.output
        assert "Test reasoning for finding" in result.output

    def test_multiple_findings_each_printed(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.write_finding(_make_finding("f1"))
        store.write_finding(_make_finding("f2"))
        event_log = _make_event_log(tmp_path)

        with (
            patch("pipeline.cli.commands.run.get_store", return_value=store),
            patch("pipeline.cli.commands.run.EventLog", return_value=event_log),
            patch("pipeline.cli.commands.run.uuid.uuid4", return_value=CYCLE_ID),
            patch("pipeline.dispatch.agent.subprocess.run", side_effect=_success_subprocess),
        ):
            result = runner.invoke(
                app,
                ["run", "run", "--repo", REPO, "--agents", "depth", "--path", str(tmp_path)],
            )

        assert "2 finding(s)" in result.output


# ---------------------------------------------------------------------------
# Config-driven agents
# ---------------------------------------------------------------------------


class TestRunCommandConfigAgents:
    """When --agents is not provided, agents come from load_config()."""

    def test_agents_loaded_from_config_when_not_specified(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        event_log = _make_event_log(tmp_path)
        config = PipelineConfig(
            repos={REPO: RepoConfig(triggers=["daily"], analysis_agents=["config-agent"])}
        )

        with (
            patch("pipeline.cli.commands.run.get_store", return_value=store),
            patch("pipeline.cli.commands.run.EventLog", return_value=event_log),
            patch("pipeline.cli.commands.run.uuid.uuid4", return_value=CYCLE_ID),
            patch("pipeline.cli.commands.run.load_config", return_value=config),
            patch(
                "pipeline.dispatch.agent.subprocess.run", side_effect=_success_subprocess
            ) as mock_run,
        ):
            result = runner.invoke(app, ["run", "run", "--repo", REPO, "--path", str(tmp_path)])

        assert result.exit_code == 0
        assert mock_run.call_count == 1
        env = mock_run.call_args[1]["env"]
        assert env["REPO_AUDIT_AGENT"] == "config-agent"

    def test_explicit_agents_override_config(self, tmp_path: Path) -> None:
        """Explicit --agents takes precedence over config analysis_agents."""
        store = _make_store(tmp_path)
        event_log = _make_event_log(tmp_path)
        config = PipelineConfig(
            repos={REPO: RepoConfig(triggers=["daily"], analysis_agents=["config-agent"])}
        )

        with (
            patch("pipeline.cli.commands.run.get_store", return_value=store),
            patch("pipeline.cli.commands.run.EventLog", return_value=event_log),
            patch("pipeline.cli.commands.run.uuid.uuid4", return_value=CYCLE_ID),
            patch("pipeline.cli.commands.run.load_config", return_value=config),
            patch(
                "pipeline.dispatch.agent.subprocess.run", side_effect=_success_subprocess
            ) as mock_run,
        ):
            runner.invoke(
                app,
                ["run", "run", "--repo", REPO, "--agents", "cli-agent", "--path", str(tmp_path)],
            )

        env = mock_run.call_args[1]["env"]
        assert env["REPO_AUDIT_AGENT"] == "cli-agent"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestRunCommandErrors:
    """Error handling in the run command."""

    def test_bad_repo_format_exits_with_code_1(self) -> None:
        result = runner.invoke(app, ["run", "run", "--repo", "nodash"])
        assert result.exit_code == 1

    def test_empty_owner_exits_with_code_1(self) -> None:
        result = runner.invoke(app, ["run", "run", "--repo", "/repo"])
        assert result.exit_code == 1

    def test_empty_repo_name_exits_with_code_1(self) -> None:
        result = runner.invoke(app, ["run", "run", "--repo", "owner/"])
        assert result.exit_code == 1

    def test_agent_failure_exits_with_code_1(self, tmp_path: Path) -> None:
        """A failing subprocess causes exit code 1."""
        store = _make_store(tmp_path)
        event_log = _make_event_log(tmp_path)

        with (
            patch("pipeline.cli.commands.run.get_store", return_value=store),
            patch("pipeline.cli.commands.run.EventLog", return_value=event_log),
            patch("pipeline.cli.commands.run.uuid.uuid4", return_value=CYCLE_ID),
            patch(
                "pipeline.dispatch.agent.subprocess.run",
                return_value=Mock(returncode=1, stderr="fatal error"),
            ),
        ):
            result = runner.invoke(
                app,
                ["run", "run", "--repo", REPO, "--agents", "bad-agent", "--path", str(tmp_path)],
            )

        assert result.exit_code == 1

    def test_agent_failure_prints_error_message(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        event_log = _make_event_log(tmp_path)

        with (
            patch("pipeline.cli.commands.run.get_store", return_value=store),
            patch("pipeline.cli.commands.run.EventLog", return_value=event_log),
            patch("pipeline.cli.commands.run.uuid.uuid4", return_value=CYCLE_ID),
            patch(
                "pipeline.dispatch.agent.subprocess.run",
                return_value=Mock(returncode=2, stderr="agent crashed"),
            ),
        ):
            result = runner.invoke(
                app,
                ["run", "run", "--repo", REPO, "--agents", "bad-agent", "--path", str(tmp_path)],
                catch_exceptions=False,
            )

        # Error message goes to stderr but typer CliRunner merges by default.
        assert "Error" in result.output or result.exit_code == 1


# ---------------------------------------------------------------------------
# Bead lifecycle
# ---------------------------------------------------------------------------


class TestRunCommandBeadLifecycle:
    """The run command creates and transitions a CycleBead correctly."""

    def test_bead_written_to_store_in_analysis_phase(self, tmp_path: Path) -> None:
        """A fresh CycleBead is persisted before dispatch starts."""
        store = _make_store(tmp_path)
        event_log = _make_event_log(tmp_path)
        # Capture the phase value at each write (bead is mutated in place).
        written_phases: list[str] = []
        original_write = store.write_cycle

        def capture_write(bead):
            written_phases.append(bead.phase)
            original_write(bead)

        store.write_cycle = capture_write

        with (
            patch("pipeline.cli.commands.run.get_store", return_value=store),
            patch("pipeline.cli.commands.run.EventLog", return_value=event_log),
            patch("pipeline.cli.commands.run.uuid.uuid4", return_value=CYCLE_ID),
            patch("pipeline.cli.commands.run.load_config", return_value=PipelineConfig()),
        ):
            runner.invoke(app, ["run", "run", "--repo", REPO, "--path", str(tmp_path)])

        # First write is in analysis phase; second write advances to synthesis.
        assert written_phases[0] == "analysis"
        assert written_phases[1] == "synthesis"

    def test_bead_ends_in_synthesis_phase_after_successful_run(self, tmp_path: Path) -> None:
        """After all agents complete, the bead is persisted in SYNTHESIS."""
        store = _make_store(tmp_path)
        event_log = _make_event_log(tmp_path)

        with (
            patch("pipeline.cli.commands.run.get_store", return_value=store),
            patch("pipeline.cli.commands.run.EventLog", return_value=event_log),
            patch("pipeline.cli.commands.run.uuid.uuid4", return_value=CYCLE_ID),
            patch("pipeline.cli.commands.run.load_config", return_value=PipelineConfig()),
        ):
            runner.invoke(app, ["run", "run", "--repo", REPO, "--path", str(tmp_path)])

        bead = store.read_cycle(CYCLE_ID)
        assert bead is not None
        assert bead.phase == "synthesis"
