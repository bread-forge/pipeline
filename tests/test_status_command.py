"""Tests for `pipeline cycle status` output format with mocked stores.

Focuses on the exact label/value format of the status output and edge cases
in event-count display. Complements the broader CLI tests in test_cli.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from beads.types import CycleBead
from typer.testing import CliRunner

from pipeline.cli.commands.cycle import _append_event
from pipeline.cli.main import app
from pipeline.store.beadstore import get_store

runner = CliRunner()


def _store(tmp_path: Path, repo: str = "owner/repo") -> object:
    return get_store(repo, beads_dir=tmp_path)


# ---------------------------------------------------------------------------
# Output label format
# ---------------------------------------------------------------------------


class TestStatusOutputLabels:
    """The status command uses specific label prefixes for each output field."""

    def test_cycle_id_label_prefix(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.write_cycle(CycleBead(cycle_id="c1", repo="owner/repo"))  # type: ignore[attr-defined]
        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(app, ["cycle", "status", "c1", "--repo", "owner/repo"])
        assert result.exit_code == 0
        assert "cycle_id:" in result.output

    def test_repo_label_prefix(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.write_cycle(CycleBead(cycle_id="c2", repo="owner/repo"))  # type: ignore[attr-defined]
        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(app, ["cycle", "status", "c2", "--repo", "owner/repo"])
        assert "repo:" in result.output

    def test_phase_label_prefix(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.write_cycle(CycleBead(cycle_id="c3", repo="owner/repo"))  # type: ignore[attr-defined]
        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(app, ["cycle", "status", "c3", "--repo", "owner/repo"])
        assert "phase:" in result.output

    def test_started_label_prefix(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.write_cycle(CycleBead(cycle_id="c4", repo="owner/repo"))  # type: ignore[attr-defined]
        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(app, ["cycle", "status", "c4", "--repo", "owner/repo"])
        assert "started:" in result.output

    def test_events_label_prefix(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.write_cycle(CycleBead(cycle_id="c5", repo="owner/repo"))  # type: ignore[attr-defined]
        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(app, ["cycle", "status", "c5", "--repo", "owner/repo"])
        assert "events:" in result.output


# ---------------------------------------------------------------------------
# Cycle ID value appears verbatim in output
# ---------------------------------------------------------------------------


class TestStatusCycleIdValue:
    """The exact cycle ID string is printed in the output."""

    def test_uuid_style_cycle_id_printed(self, tmp_path: Path) -> None:
        cycle_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        store = _store(tmp_path)
        store.write_cycle(CycleBead(cycle_id=cycle_id, repo="owner/repo"))  # type: ignore[attr-defined]
        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(app, ["cycle", "status", cycle_id, "--repo", "owner/repo"])
        assert cycle_id in result.output

    def test_short_cycle_id_printed(self, tmp_path: Path) -> None:
        cycle_id = "short"
        store = _store(tmp_path)
        store.write_cycle(CycleBead(cycle_id=cycle_id, repo="owner/repo"))  # type: ignore[attr-defined]
        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(app, ["cycle", "status", cycle_id, "--repo", "owner/repo"])
        assert cycle_id in result.output


# ---------------------------------------------------------------------------
# Phase values
# ---------------------------------------------------------------------------


class TestStatusPhaseValues:
    """All valid phase values are printed exactly as stored."""

    @pytest.mark.parametrize(
        "phase",
        ["analysis", "synthesis", "gate", "execution", "verification", "complete"],
    )
    def test_phase_value_printed_verbatim(self, phase: str, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.write_cycle(CycleBead(cycle_id="c-phase", repo="owner/repo", phase=phase))  # type: ignore[attr-defined]
        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(app, ["cycle", "status", "c-phase", "--repo", "owner/repo"])
        assert phase in result.output


# ---------------------------------------------------------------------------
# Event count line format
# ---------------------------------------------------------------------------


class TestStatusEventCountFormat:
    """The events line includes count and the word 'total'."""

    def test_events_line_format_with_zero_events(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.write_cycle(CycleBead(cycle_id="c-zero", repo="owner/repo"))  # type: ignore[attr-defined]
        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(app, ["cycle", "status", "c-zero", "--repo", "owner/repo"])
        assert "0 total" in result.output

    def test_events_line_format_with_one_event(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.write_cycle(CycleBead(cycle_id="c-one", repo="owner/repo"))  # type: ignore[attr-defined]
        log = tmp_path / "events" / "owner" / "repo" / "c-one.jsonl"
        _append_event(log, {"event_type": "cycle_started"})
        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(app, ["cycle", "status", "c-one", "--repo", "owner/repo"])
        assert "1 total" in result.output

    def test_events_line_format_with_multiple_events(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.write_cycle(CycleBead(cycle_id="c-many", repo="owner/repo"))  # type: ignore[attr-defined]
        log = tmp_path / "events" / "owner" / "repo" / "c-many.jsonl"
        for _ in range(7):
            _append_event(log, {"event_type": "finding_added"})
        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(app, ["cycle", "status", "c-many", "--repo", "owner/repo"])
        assert "7 total" in result.output


# ---------------------------------------------------------------------------
# Per-event-type breakdown format
# ---------------------------------------------------------------------------


class TestStatusEventBreakdownFormat:
    """Per-type event counts are indented with two spaces and formatted as 'type: N'."""

    def test_breakdown_entry_uses_colon_space_count(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.write_cycle(CycleBead(cycle_id="c-fmt", repo="owner/repo"))  # type: ignore[attr-defined]
        log = tmp_path / "events" / "owner" / "repo" / "c-fmt.jsonl"
        _append_event(log, {"event_type": "alpha_event"})
        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(app, ["cycle", "status", "c-fmt", "--repo", "owner/repo"])
        assert "alpha_event: 1" in result.output

    def test_breakdown_entries_sorted_alphabetically(self, tmp_path: Path) -> None:
        """Event type breakdown is printed in alphabetical order."""
        store = _store(tmp_path)
        store.write_cycle(CycleBead(cycle_id="c-sort", repo="owner/repo"))  # type: ignore[attr-defined]
        log = tmp_path / "events" / "owner" / "repo" / "c-sort.jsonl"
        _append_event(log, {"event_type": "zebra_event"})
        _append_event(log, {"event_type": "alpha_event"})
        _append_event(log, {"event_type": "middle_event"})
        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(app, ["cycle", "status", "c-sort", "--repo", "owner/repo"])
        lines = result.output.splitlines()
        breakdown = [ln for ln in lines if ln.startswith("  ")]
        event_names = [ln.strip().split(":")[0] for ln in breakdown]
        assert event_names == sorted(event_names)

    def test_multiple_event_types_all_listed(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.write_cycle(CycleBead(cycle_id="c-multi", repo="owner/repo"))  # type: ignore[attr-defined]
        log = tmp_path / "events" / "owner" / "repo" / "c-multi.jsonl"
        _append_event(log, {"event_type": "type_a"})
        _append_event(log, {"event_type": "type_b"})
        _append_event(log, {"event_type": "type_a"})
        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(app, ["cycle", "status", "c-multi", "--repo", "owner/repo"])
        assert "type_a: 2" in result.output
        assert "type_b: 1" in result.output


# ---------------------------------------------------------------------------
# Repo value display
# ---------------------------------------------------------------------------


class TestStatusRepoValue:
    """The full 'owner/repo' string appears in the output."""

    def test_repo_with_hyphens_displayed(self, tmp_path: Path) -> None:
        repo = "my-org/my-service"
        store = _store(tmp_path, repo=repo)
        store.write_cycle(CycleBead(cycle_id="c-repo", repo=repo))  # type: ignore[attr-defined]
        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(app, ["cycle", "status", "c-repo", "--repo", repo])
        assert repo in result.output

    def test_repo_value_matches_stored_bead(self, tmp_path: Path) -> None:
        repo = "acme/widget"
        store = _store(tmp_path, repo=repo)
        store.write_cycle(CycleBead(cycle_id="c-val", repo=repo))  # type: ignore[attr-defined]
        with (
            patch("pipeline.cli.commands.cycle.get_store", return_value=store),
            patch("pipeline.cli.commands.cycle.EVENTS_DIR", tmp_path / "events"),
        ):
            result = runner.invoke(app, ["cycle", "status", "c-val", "--repo", repo])
        assert repo in result.output


# ---------------------------------------------------------------------------
# Error output format
# ---------------------------------------------------------------------------


class TestStatusErrorFormat:
    """Error messages for missing cycles contain the unknown cycle ID."""

    def test_error_message_includes_missing_cycle_id(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        with patch("pipeline.cli.commands.cycle.get_store", return_value=store):
            result = runner.invoke(
                app,
                ["cycle", "status", "definitely-not-there", "--repo", "owner/repo"],
            )
        assert result.exit_code == 1
        assert "definitely-not-there" in result.output

    def test_bad_repo_format_error_includes_repo_string(self) -> None:
        result = runner.invoke(app, ["cycle", "status", "some-id", "--repo", "no-slash-here"])
        assert result.exit_code == 1
        assert "no-slash-here" in result.output
