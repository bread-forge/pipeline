"""Tests for the data layer underlying the `pipeline telemetry` CLI output.

The `pipeline telemetry --repo <owner/repo> [--last N]` command (issue #55) will
read records from TelemetryStore and display a tabular view with columns:
date, proposals, approved%, rejected%, and cost.

These tests verify that TelemetryStore produces records with the correct fields
and that slicing to --last N returns the expected subset.  They ensure the
underlying store contract is stable so the CLI command can be implemented
against it without surprises.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.telemetry.store import TelemetryStore

# Default value from issue #55 spec: `pipeline telemetry` shows last 10 records.
DEFAULT_LAST_N = 10

# Required fields for a telemetry record that the CLI would display as a table row.
REQUIRED_RECORD_FIELDS = frozenset(
    {
        "cycle_id",
        "date",
        "proposal_count",
        "approved_rate",
        "rejected_rate",
        "total_cost_usd",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    cycle_id: str,
    date: str = "2024-01-01",
    proposal_count: int = 0,
    approved_rate: float = 0.0,
    rejected_rate: float = 0.0,
    total_cost_usd: float = 0.0,
) -> dict:
    return {
        "cycle_id": cycle_id,
        "date": date,
        "proposal_count": proposal_count,
        "approved_rate": approved_rate,
        "rejected_rate": rejected_rate,
        "total_cost_usd": total_cost_usd,
    }


# ---------------------------------------------------------------------------
# Record shape validation
# ---------------------------------------------------------------------------


class TestTelemetryRecordFields:
    """Telemetry records must include all fields required by the CLI table display."""

    def test_required_fields_are_present_after_round_trip(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        record = _make_record("c1")
        store.append(record)
        [loaded] = store.read_all()
        for field in REQUIRED_RECORD_FIELDS:
            assert field in loaded, f"Required field {field!r} missing from loaded record"

    def test_approved_rate_is_numeric(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append(_make_record("c1", approved_rate=0.75))
        [rec] = store.read_all()
        assert isinstance(rec["approved_rate"], (int, float))

    def test_rejected_rate_is_numeric(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append(_make_record("c1", rejected_rate=0.25))
        [rec] = store.read_all()
        assert isinstance(rec["rejected_rate"], (int, float))

    def test_total_cost_usd_is_numeric(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append(_make_record("c1", total_cost_usd=3.14))
        [rec] = store.read_all()
        assert isinstance(rec["total_cost_usd"], (int, float))

    def test_proposal_count_is_integer(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append(_make_record("c1", proposal_count=5))
        [rec] = store.read_all()
        assert rec["proposal_count"] == 5

    def test_date_field_is_string(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append(_make_record("c1", date="2024-03-15"))
        [rec] = store.read_all()
        assert isinstance(rec["date"], str)

    def test_cycle_id_preserved_exactly(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append(_make_record("my-exact-cycle-id"))
        [rec] = store.read_all()
        assert rec["cycle_id"] == "my-exact-cycle-id"


# ---------------------------------------------------------------------------
# Last-N slicing (--last N behaviour)
# ---------------------------------------------------------------------------


class TestLastNSlicing:
    """The telemetry command's --last N option returns the N most recent records."""

    def test_last_n_returns_n_records_from_end(self, tmp_path: Path) -> None:
        """Slicing the last N records from a store returns the most recent N."""
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        for i in range(20):
            store.append(_make_record(f"c{i}", date=f"2024-01-{i + 1:02d}"))
        all_records = store.read_all()
        last_10 = all_records[-DEFAULT_LAST_N:]
        assert len(last_10) == DEFAULT_LAST_N
        assert last_10[-1]["cycle_id"] == "c19"

    def test_last_n_when_fewer_records_than_n(self, tmp_path: Path) -> None:
        """If fewer than N records exist, all records are returned."""
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        for i in range(3):
            store.append(_make_record(f"c{i}"))
        all_records = store.read_all()
        last_10 = all_records[-DEFAULT_LAST_N:]
        assert len(last_10) == 3

    def test_last_1_returns_most_recent_record(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append(_make_record("first"))
        store.append(_make_record("second"))
        store.append(_make_record("third"))
        all_records = store.read_all()
        assert all_records[-1]["cycle_id"] == "third"

    def test_last_n_preserves_insertion_order_within_window(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        for i in range(15):
            store.append(_make_record(f"c{i}"))
        all_records = store.read_all()
        last_5 = all_records[-5:]
        assert [r["cycle_id"] for r in last_5] == [f"c{i}" for i in range(10, 15)]

    def test_empty_store_returns_empty_slice(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        all_records = store.read_all()
        assert all_records[-DEFAULT_LAST_N:] == []

    def test_last_n_exactly_n_records(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        for i in range(DEFAULT_LAST_N):
            store.append(_make_record(f"c{i}"))
        all_records = store.read_all()
        last_n = all_records[-DEFAULT_LAST_N:]
        assert len(last_n) == DEFAULT_LAST_N
        assert last_n[0]["cycle_id"] == "c0"
        assert last_n[-1]["cycle_id"] == f"c{DEFAULT_LAST_N - 1}"


# ---------------------------------------------------------------------------
# Per-repo isolation
# ---------------------------------------------------------------------------


class TestPerRepoIsolation:
    """Each (owner, repo) pair has its own telemetry file; stores don't cross-contaminate."""

    def test_different_repos_write_to_different_files(self, tmp_path: Path) -> None:
        store_a = TelemetryStore("owner", "repo-a", base_dir=tmp_path)
        store_b = TelemetryStore("owner", "repo-b", base_dir=tmp_path)
        assert store_a.path != store_b.path

    def test_records_isolated_between_repos(self, tmp_path: Path) -> None:
        store_a = TelemetryStore("owner", "repo-a", base_dir=tmp_path)
        store_b = TelemetryStore("owner", "repo-b", base_dir=tmp_path)
        store_a.append(_make_record("cycle-in-a"))
        assert store_b.read_all() == []

    def test_different_owners_have_separate_files(self, tmp_path: Path) -> None:
        store_x = TelemetryStore("org-x", "app", base_dir=tmp_path)
        store_y = TelemetryStore("org-y", "app", base_dir=tmp_path)
        store_x.append(_make_record("x-cycle"))
        assert store_y.read_all() == []

    def test_reading_back_from_correct_store(self, tmp_path: Path) -> None:
        store = TelemetryStore("myorg", "myrepo", base_dir=tmp_path)
        store.append(_make_record("targeted-cycle"))
        other = TelemetryStore("myorg", "other", base_dir=tmp_path)
        assert other.read_all() == []
        [rec] = store.read_all()
        assert rec["cycle_id"] == "targeted-cycle"


# ---------------------------------------------------------------------------
# Display-column value accuracy
# ---------------------------------------------------------------------------


class TestDisplayColumnValues:
    """Values stored in records are the exact values a CLI table would display."""

    def test_zero_cost_stored_and_retrieved(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append(_make_record("c1", total_cost_usd=0.0))
        [rec] = store.read_all()
        assert rec["total_cost_usd"] == pytest.approx(0.0)

    def test_high_precision_cost_survives_json_round_trip(self, tmp_path: Path) -> None:
        cost = 12.345678
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append(_make_record("c1", total_cost_usd=cost))
        [rec] = store.read_all()
        assert rec["total_cost_usd"] == pytest.approx(cost)

    def test_full_approval_rate_stored_as_float(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append(_make_record("c1", approved_rate=1.0))
        [rec] = store.read_all()
        assert rec["approved_rate"] == pytest.approx(1.0)

    def test_zero_proposal_count_stored(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append(_make_record("c1", proposal_count=0))
        [rec] = store.read_all()
        assert rec["proposal_count"] == 0

    def test_large_proposal_count_stored(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append(_make_record("c1", proposal_count=999))
        [rec] = store.read_all()
        assert rec["proposal_count"] == 999

    def test_date_string_preserved_verbatim(self, tmp_path: Path) -> None:
        date_str = "2025-12-31T23:59:59+00:00"
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append(_make_record("c1", date=date_str))
        [rec] = store.read_all()
        assert rec["date"] == date_str
