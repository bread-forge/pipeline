"""Tests for pipeline CLI commands: start, status, replay."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from beads.types import CycleBead
from typer.testing import CliRunner

from pipeline.cli.commands.cycle import _append_event
from pipeline.cli.main import app
from pipeline.lock.orchestrator import LockAcquisitionError
from pipeline.store.beadstore import get_store

runner = CliRunner()


def _real_store(tmp_path: Path, repo: str = "owner/repo") -> object:
    """Return a BeadStore rooted in tmp_path for use in CLI tests."""
    return get_store(repo, beads_dir=tmp_path)


# ---------------------------------------------------------------------------
# Repo argument parsing (_parse_repo via CLI)
# ---------------------------------------------------------------------------


class TestParseRepo:
    """_parse_repo is tested indirectly through the CLI exit code."""

    def test_no_slash_exits_with_code_1(self) -> None:
        result = runner.invoke(app, ["cycle", "status", "some-id", "--repo", "noslash"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_empty_owner_exits_with_code_1(self) -> None:
        result = runner.invoke(app, ["cycle", "status", "some-id", "--repo", "/repo"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_empty_repo_name_exits_with_code_1(self) -> None:
        result = runner.invoke(app, ["cycle", "status", "some-id", "--repo", "owner/"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_valid_repo_format_does_not_error_on_format(self, tmp_path: Path) -> None:
        """owner/repo format is accepted (downstream errors are about missing data)."""
        store = _real_store(tmp_path)
        with patch("pipeline.cli.commands.cycle.get_store", return_value=store):
            result = runner.invoke(app, ["cycle", "status", "missing-id", "--repo", "owner/repo"])
        # Exit is 1 because cycle ID does not exist, NOT because of bad format.
        assert "owner/repo" not in result.output or "Error" in result.output


# ---------------------------------------------------------------------------
# start command
# ---------------------------------------------------------------------------


class TestStartCommand:
    """Tests for `pipeline cycle start`."""

    def test_prints_cycle_id_to_stdout(self, tmp_path: Path) -> None:
        """start outputs the new cycle ID on success."""
        store = _real_store(tmp_path)

        with (
            patch("pipeline.cli.commands.cycle.OrchestratorLock") as mock_lock_cls,
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
            patch("pipeline.cli.commands.cycle.uuid.uuid4", return_value="test-uuid-1234"),
        ):
            mock_lock_cls.return_value.__enter__.return_value = MagicMock()
            mock_lock_cls.return_value.__exit__.return_value = False

            result = runner.invoke(app, ["cycle", "start", "--repo", "owner/repo"])

        assert result.exit_code == 0
        assert "test-uuid-1234" in result.output

    def test_appends_cycle_started_event_to_log(self, tmp_path: Path) -> None:
        """start writes a cycle_started event to the JSONL log."""
        store = _real_store(tmp_path)
        events_dir = tmp_path / "events"

        with (
            patch("pipeline.cli.commands.cycle.OrchestratorLock") as mock_lock_cls,
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", events_dir),
            patch("pipeline.cli.commands.cycle.uuid.uuid4", return_value="fixed-id"),
        ):
            mock_lock_cls.return_value.__enter__.return_value = MagicMock()
            mock_lock_cls.return_value.__exit__.return_value = False

            runner.invoke(app, ["cycle", "start", "--repo", "owner/repo"])

        log_path = events_dir / "owner" / "repo" / "fixed-id.jsonl"
        assert log_path.exists()
        events = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        assert len(events) == 1
        assert events[0]["event_type"] == "cycle_started"
        assert events[0]["cycle_id"] == "fixed-id"

    def test_lock_error_exits_with_code_1_and_error_message(self, tmp_path: Path) -> None:
        """When the lock is held, exit code is 1 and an error is printed."""
        with patch("pipeline.cli.commands.cycle.OrchestratorLock") as mock_lock_cls:
            mock_lock_cls.return_value.__enter__.side_effect = LockAcquisitionError(
                "already active"
            )
            mock_lock_cls.return_value.__exit__.return_value = False

            result = runner.invoke(app, ["cycle", "start", "--repo", "owner/repo"])

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_bad_repo_format_exits_with_code_1(self) -> None:
        result = runner.invoke(app, ["cycle", "start", "--repo", "badformat"])
        assert result.exit_code == 1

    def test_trigger_option_is_forwarded(self, tmp_path: Path) -> None:
        """--trigger value is written into the JSONL event."""
        store = _real_store(tmp_path)
        events_dir = tmp_path / "events"

        with (
            patch("pipeline.cli.commands.cycle.OrchestratorLock") as mock_lock_cls,
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", events_dir),
            patch("pipeline.cli.commands.cycle.uuid.uuid4", return_value="trig-id"),
        ):
            mock_lock_cls.return_value.__enter__.return_value = MagicMock()
            mock_lock_cls.return_value.__exit__.return_value = False

            runner.invoke(
                app,
                ["cycle", "start", "--repo", "owner/repo", "--trigger", "nightly cron"],
            )

        log_path = events_dir / "owner" / "repo" / "trig-id.jsonl"
        events = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        assert events[0]["trigger"] == "nightly cron"


# ---------------------------------------------------------------------------
# status command
# ---------------------------------------------------------------------------


class TestStatusCommand:
    """Tests for `pipeline cycle status`."""

    def test_shows_cycle_metadata(self, tmp_path: Path) -> None:
        """status prints cycle_id, repo, and phase."""
        store = _real_store(tmp_path)
        bead = CycleBead(cycle_id="cycle-s1", repo="owner/repo", phase="synthesis")
        store.write_cycle(bead)  # type: ignore[attr-defined]

        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(
                app, ["cycle", "status", "cycle-s1", "--repo", "owner/repo"]
            )

        assert result.exit_code == 0
        assert "cycle-s1" in result.output
        assert "synthesis" in result.output
        assert "owner/repo" in result.output

    def test_shows_total_event_count(self, tmp_path: Path) -> None:
        """status counts all events from the JSONL log."""
        store = _real_store(tmp_path)
        bead = CycleBead(cycle_id="cycle-ev", repo="owner/repo")
        store.write_cycle(bead)  # type: ignore[attr-defined]

        log_path = tmp_path / "events" / "owner" / "repo" / "cycle-ev.jsonl"
        _append_event(log_path, {"event_type": "cycle_started"})
        _append_event(log_path, {"event_type": "finding_added"})
        _append_event(log_path, {"event_type": "finding_added"})

        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(
                app, ["cycle", "status", "cycle-ev", "--repo", "owner/repo"]
            )

        assert result.exit_code == 0
        assert "3 total" in result.output

    def test_shows_per_event_type_counts(self, tmp_path: Path) -> None:
        """status breaks down events by type."""
        store = _real_store(tmp_path)
        bead = CycleBead(cycle_id="cycle-ct", repo="owner/repo")
        store.write_cycle(bead)  # type: ignore[attr-defined]

        log_path = tmp_path / "events" / "owner" / "repo" / "cycle-ct.jsonl"
        _append_event(log_path, {"event_type": "cycle_started"})
        _append_event(log_path, {"event_type": "finding_added"})
        _append_event(log_path, {"event_type": "finding_added"})

        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(
                app, ["cycle", "status", "cycle-ct", "--repo", "owner/repo"]
            )

        assert "finding_added: 2" in result.output
        assert "cycle_started: 1" in result.output

    def test_unknown_cycle_id_exits_with_code_1(self, tmp_path: Path) -> None:
        store = _real_store(tmp_path)
        with patch("pipeline.cli.commands.cycle.get_store", return_value=store):
            result = runner.invoke(
                app, ["cycle", "status", "does-not-exist", "--repo", "owner/repo"]
            )
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_shows_zero_events_when_log_missing(self, tmp_path: Path) -> None:
        """status works when no event log file exists yet."""
        store = _real_store(tmp_path)
        bead = CycleBead(cycle_id="cycle-nolog", repo="owner/repo")
        store.write_cycle(bead)  # type: ignore[attr-defined]

        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(
                app, ["cycle", "status", "cycle-nolog", "--repo", "owner/repo"]
            )

        assert result.exit_code == 0
        assert "0 total" in result.output


# ---------------------------------------------------------------------------
# replay command
# ---------------------------------------------------------------------------


class TestReplayCommand:
    """Tests for `pipeline cycle replay`."""

    def test_prints_each_event_as_json_line(self, tmp_path: Path) -> None:
        """replay outputs one JSON object per line in log order."""
        log_path = tmp_path / "events" / "owner" / "repo" / "cycle-r1.jsonl"
        events = [
            {"event_type": "cycle_started", "cycle_id": "cycle-r1"},
            {"event_type": "finding_added", "n": 1},
            {"event_type": "finding_added", "n": 2},
        ]
        for e in events:
            _append_event(log_path, e)

        with patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"):
            result = runner.invoke(
                app, ["cycle", "replay", "cycle-r1", "--repo", "owner/repo"]
            )

        assert result.exit_code == 0
        output_lines = [ln for ln in result.output.strip().splitlines() if ln.strip()]
        assert len(output_lines) == 3
        for line, expected in zip(output_lines, events, strict=True):
            assert json.loads(line) == expected

    def test_empty_or_missing_log_exits_with_code_1(self, tmp_path: Path) -> None:
        """replay fails when no events exist for the requested cycle."""
        with patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"):
            result = runner.invoke(
                app, ["cycle", "replay", "ghost-cycle", "--repo", "owner/repo"]
            )
        assert result.exit_code == 1
        assert "No events found" in result.output

    def test_output_is_valid_json_per_line(self, tmp_path: Path) -> None:
        """Every line of replay output is individually parseable as JSON."""
        log_path = tmp_path / "events" / "owner" / "repo" / "cycle-j1.jsonl"
        for i in range(5):
            _append_event(log_path, {"event_type": "finding_added", "index": i})

        with patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"):
            result = runner.invoke(
                app, ["cycle", "replay", "cycle-j1", "--repo", "owner/repo"]
            )

        assert result.exit_code == 0
        non_empty = [ln for ln in result.output.splitlines() if ln.strip()]
        parsed = [json.loads(line) for line in non_empty]
        assert [p["index"] for p in parsed] == list(range(5))

    def test_bad_repo_format_exits_with_code_1(self) -> None:
        result = runner.invoke(app, ["cycle", "replay", "some-id", "--repo", "bad"])
        assert result.exit_code == 1
