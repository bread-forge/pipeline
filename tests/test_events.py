"""Tests for EventLog append/replay in pipeline.cli.commands.cycle."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.cli.commands.cycle import _append_event, _read_events


class TestAppendEvent:
    """Tests for _append_event — JSONL append with directory creation."""

    def test_creates_file_and_appends_json_line(self, tmp_path: Path) -> None:
        """A single appended event lands on disk as valid JSON."""
        log_path = tmp_path / "events" / "cycle.jsonl"
        event = {"event_type": "cycle_started", "cycle_id": "abc123"}

        _append_event(log_path, event)

        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0]) == event

    def test_appends_multiple_events_in_order(self, tmp_path: Path) -> None:
        """Multiple appends produce one line per event, in call order."""
        log_path = tmp_path / "cycle.jsonl"
        events = [
            {"event_type": "cycle_started", "n": 1},
            {"event_type": "finding_added", "n": 2},
            {"event_type": "proposal_added", "n": 3},
        ]

        for e in events:
            _append_event(log_path, e)

        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3
        for line, expected in zip(lines, events, strict=True):
            assert json.loads(line) == expected

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Missing intermediate directories are created automatically."""
        log_path = tmp_path / "a" / "b" / "c" / "cycle.jsonl"
        _append_event(log_path, {"event_type": "test"})
        assert log_path.exists()

    def test_preserves_nested_metadata(self, tmp_path: Path) -> None:
        """Arbitrary JSON-serialisable metadata survives the round-trip."""
        log_path = tmp_path / "cycle.jsonl"
        event = {"event_type": "finding_added", "meta": {"agent": "repo-audit", "cost": 0.05}}

        _append_event(log_path, event)

        parsed = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert parsed == event


class TestReadEvents:
    """Tests for _read_events — JSONL reader."""

    def test_returns_empty_list_when_file_does_not_exist(self, tmp_path: Path) -> None:
        """Missing log file is not an error; returns empty list."""
        log_path = tmp_path / "nonexistent.jsonl"
        assert _read_events(log_path) == []

    def test_round_trip_single_event(self, tmp_path: Path) -> None:
        """Written event is readable via _read_events."""
        log_path = tmp_path / "cycle.jsonl"
        event = {"event_type": "cycle_started", "cycle_id": "xyz"}

        _append_event(log_path, event)

        assert _read_events(log_path) == [event]

    def test_round_trip_multiple_events(self, tmp_path: Path) -> None:
        """Order is preserved across multiple append/read cycles."""
        log_path = tmp_path / "cycle.jsonl"
        events = [
            {"event_type": "a"},
            {"event_type": "b", "data": 42},
            {"event_type": "c", "nested": {"x": [1, 2, 3]}},
        ]
        for e in events:
            _append_event(log_path, e)

        assert _read_events(log_path) == events

    def test_skips_blank_lines(self, tmp_path: Path) -> None:
        """Blank lines in the JSONL file are silently ignored."""
        log_path = tmp_path / "cycle.jsonl"
        log_path.write_text(
            '{"event_type": "a"}\n\n{"event_type": "b"}\n',
            encoding="utf-8",
        )

        result = _read_events(log_path)

        assert result == [{"event_type": "a"}, {"event_type": "b"}]

    def test_reads_events_appended_across_separate_calls(self, tmp_path: Path) -> None:
        """Events written in distinct _append_event calls are all returned."""
        log_path = tmp_path / "cycle.jsonl"
        _append_event(log_path, {"event_type": "first"})
        _append_event(log_path, {"event_type": "second"})
        _append_event(log_path, {"event_type": "third"})

        result = _read_events(log_path)

        assert len(result) == 3
        assert result[0]["event_type"] == "first"
        assert result[2]["event_type"] == "third"
