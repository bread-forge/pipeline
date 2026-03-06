"""Tests for OrchestratorLock concurrent-acquisition rejection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline.lock.orchestrator import LockAcquisitionError, OrchestratorLock


class TestOrchestratorLockAcquisition:
    """Tests for successful lock acquisition and context manager behaviour."""

    def test_acquires_lock_and_returns_self(self, tmp_path: Path) -> None:
        """Lock can be acquired when no other holder exists."""
        with patch("pipeline.lock.orchestrator.LOCKS_DIR", tmp_path), OrchestratorLock("owner", "repo") as lock:
            assert lock._fd is not None

    def test_releases_lock_on_context_exit(self, tmp_path: Path) -> None:
        """fd is set to None after the context manager exits normally."""
        with patch("pipeline.lock.orchestrator.LOCKS_DIR", tmp_path):
            lock = OrchestratorLock("owner", "repo")
            with lock:
                pass
            assert lock._fd is None

    def test_can_reacquire_after_release(self, tmp_path: Path) -> None:
        """A released lock can be acquired again in the same process."""
        with patch("pipeline.lock.orchestrator.LOCKS_DIR", tmp_path):
            with OrchestratorLock("owner", "repo"):
                pass
            # Second acquisition must succeed — the first was released.
            with OrchestratorLock("owner", "repo"):
                pass

    def test_lock_file_path_includes_owner_and_repo(self, tmp_path: Path) -> None:
        """Lock file is named '{owner}-{repo}.lock' under LOCKS_DIR."""
        with patch("pipeline.lock.orchestrator.LOCKS_DIR", tmp_path):
            lock = OrchestratorLock("bread-forge", "pipeline")
            assert lock._lock_path == tmp_path / "bread-forge-pipeline.lock"

    def test_lock_file_created_on_acquisition(self, tmp_path: Path) -> None:
        """The lock file is present on disk after acquisition."""
        with patch("pipeline.lock.orchestrator.LOCKS_DIR", tmp_path), OrchestratorLock("owner", "repo"):
            assert (tmp_path / "owner-repo.lock").exists()

    def test_locks_dir_created_if_missing(self, tmp_path: Path) -> None:
        """LOCKS_DIR and any missing parents are created automatically."""
        nested = tmp_path / "deep" / "nested"
        with patch("pipeline.lock.orchestrator.LOCKS_DIR", nested), OrchestratorLock("owner", "repo"):
            assert nested.is_dir()


class TestOrchestratorLockRejection:
    """Tests for concurrent-acquisition rejection."""

    def test_blocking_io_error_raises_lock_acquisition_error(self, tmp_path: Path) -> None:
        """When flock raises BlockingIOError, LockAcquisitionError is raised."""
        import fcntl

        with (
            patch("pipeline.lock.orchestrator.LOCKS_DIR", tmp_path),
            patch.object(fcntl, "flock", side_effect=BlockingIOError("already locked")),
            pytest.raises(LockAcquisitionError, match="Another pipeline cycle"),
            OrchestratorLock("owner", "repo"),
        ):
            pass

    def test_error_message_includes_owner_and_repo(self, tmp_path: Path) -> None:
        """LockAcquisitionError message names the repo that is locked."""
        import fcntl

        with (
            patch("pipeline.lock.orchestrator.LOCKS_DIR", tmp_path),
            patch.object(fcntl, "flock", side_effect=BlockingIOError("busy")),
            pytest.raises(LockAcquisitionError, match="bread-forge/my-repo"),
            OrchestratorLock("bread-forge", "my-repo"),
        ):
            pass

    def test_fd_closed_when_acquisition_fails(self, tmp_path: Path) -> None:
        """The file descriptor is closed and _fd reset to None on failure."""
        import fcntl

        with (
            patch("pipeline.lock.orchestrator.LOCKS_DIR", tmp_path),
            patch.object(fcntl, "flock", side_effect=BlockingIOError("busy")),
        ):
            lock = OrchestratorLock("owner", "repo")
            with pytest.raises(LockAcquisitionError):
                lock.__enter__()
            assert lock._fd is None

    def test_exit_is_safe_when_fd_is_none(self, tmp_path: Path) -> None:
        """__exit__ with _fd=None does not raise."""
        with patch("pipeline.lock.orchestrator.LOCKS_DIR", tmp_path):
            lock = OrchestratorLock("owner", "repo")
        lock._fd = None
        # Must not raise even though no lock was held.
        lock.__exit__(None, None, None)
