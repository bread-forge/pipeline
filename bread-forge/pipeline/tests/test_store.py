"""Tests for BeadStore helpers in pipeline.store."""

from __future__ import annotations

from pathlib import Path

import pytest
from beads.store import BeadStore
from beads.types import CycleBead

from pipeline.store.beadstore import get_store, read_cycle, write_cycle


class TestGetStore:
    """Tests for get_store factory."""

    def test_returns_bead_store_instance(self, tmp_path: Path) -> None:
        store = get_store("owner/repo", beads_dir=tmp_path)
        assert isinstance(store, BeadStore)

    def test_creates_repo_directory_under_beads_dir(self, tmp_path: Path) -> None:
        get_store("owner/repo", beads_dir=tmp_path)
        assert (tmp_path / "owner" / "repo").is_dir()

    def test_different_repos_produce_different_roots(self, tmp_path: Path) -> None:
        store_a = get_store("owner/alpha", beads_dir=tmp_path)
        store_b = get_store("owner/beta", beads_dir=tmp_path)
        assert store_a._root != store_b._root

    def test_same_repo_called_twice_uses_same_root(self, tmp_path: Path) -> None:
        store_a = get_store("owner/repo", beads_dir=tmp_path)
        store_b = get_store("owner/repo", beads_dir=tmp_path)
        assert store_a._root == store_b._root


class TestWriteCycle:
    """Tests for write_cycle helper."""

    def test_persists_cycle_bead_as_json_file(self, tmp_path: Path) -> None:
        store = get_store("owner/repo", beads_dir=tmp_path)
        bead = CycleBead(cycle_id="cycle-1", repo="owner/repo")

        write_cycle(store, bead)

        expected_path = tmp_path / "owner" / "repo" / "cycles" / "cycle-1.json"
        assert expected_path.exists()

    def test_write_sets_updated_at(self, tmp_path: Path) -> None:
        """write_cycle calls touch() which refreshes updated_at on disk."""
        store = get_store("owner/repo", beads_dir=tmp_path)
        bead = CycleBead(cycle_id="cycle-ts", repo="owner/repo")
        original_updated_at = bead.updated_at

        write_cycle(store, bead)

        on_disk = read_cycle(store, "cycle-ts")
        assert on_disk is not None
        assert on_disk.updated_at >= original_updated_at

    def test_write_overwrites_existing_bead(self, tmp_path: Path) -> None:
        """Writing a bead twice replaces the previous content."""
        store = get_store("owner/repo", beads_dir=tmp_path)
        bead = CycleBead(cycle_id="cycle-upd", repo="owner/repo", phase="analysis")
        write_cycle(store, bead)

        bead.phase = "gate"
        write_cycle(store, bead)

        result = read_cycle(store, "cycle-upd")
        assert result is not None
        assert result.phase == "gate"


class TestReadCycle:
    """Tests for read_cycle helper."""

    def test_returns_none_for_unknown_cycle_id(self, tmp_path: Path) -> None:
        store = get_store("owner/repo", beads_dir=tmp_path)
        assert read_cycle(store, "does-not-exist") is None

    def test_round_trip_preserves_all_fields(self, tmp_path: Path) -> None:
        store = get_store("owner/repo", beads_dir=tmp_path)
        bead = CycleBead(
            cycle_id="cycle-abc",
            repo="owner/repo",
            phase="synthesis",
            trigger="manual test run",
            finding_count=5,
            proposal_count=2,
            total_cost_usd=0.42,
        )

        write_cycle(store, bead)
        result = read_cycle(store, "cycle-abc")

        assert result is not None
        assert result.cycle_id == "cycle-abc"
        assert result.repo == "owner/repo"
        assert result.phase == "synthesis"
        assert result.trigger == "manual test run"
        assert result.finding_count == 5
        assert result.proposal_count == 2
        assert result.total_cost_usd == pytest.approx(0.42)

    def test_reads_correct_bead_when_multiple_exist(self, tmp_path: Path) -> None:
        """read_cycle returns only the bead matching the requested cycle_id."""
        store = get_store("owner/repo", beads_dir=tmp_path)
        bead_a = CycleBead(cycle_id="cycle-aaa", repo="owner/repo", phase="analysis")
        bead_b = CycleBead(cycle_id="cycle-bbb", repo="owner/repo", phase="gate")
        write_cycle(store, bead_a)
        write_cycle(store, bead_b)

        result = read_cycle(store, "cycle-bbb")

        assert result is not None
        assert result.cycle_id == "cycle-bbb"
        assert result.phase == "gate"

    def test_returns_none_after_wrong_repo(self, tmp_path: Path) -> None:
        """A bead written to one repo is not visible via a different repo's store."""
        store_a = get_store("owner/alpha", beads_dir=tmp_path)
        store_b = get_store("owner/beta", beads_dir=tmp_path)
        bead = CycleBead(cycle_id="cycle-x", repo="owner/alpha")
        write_cycle(store_a, bead)

        assert read_cycle(store_b, "cycle-x") is None
