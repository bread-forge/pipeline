"""Exclusive lock preventing concurrent pipeline orchestrator cycles."""

import fcntl
import os
from pathlib import Path
from types import TracebackType

LOCKS_DIR = Path.home() / ".pipeline" / "locks"


class LockAcquisitionError(Exception):
    """Raised when another pipeline cycle is already active for this repo."""


class OrchestratorLock:
    """Exclusive lock preventing concurrent pipeline cycles for a given repo.

    Uses fcntl.flock for advisory locking on ~/.pipeline/locks/{owner}-{repo}.lock.
    Raises LockAcquisitionError immediately if another cycle holds the lock.

    Usage::

        with OrchestratorLock("bread-forge", "pipeline"):
            run_cycle()
    """

    def __init__(self, owner: str, repo: str) -> None:
        self._owner = owner
        self._repo = repo
        self._lock_path = LOCKS_DIR / f"{owner}-{repo}.lock"
        self._fd: int | None = None

    def __enter__(self) -> "OrchestratorLock":
        LOCKS_DIR.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self._fd)
            self._fd = None
            raise LockAcquisitionError(
                f"Another pipeline cycle is already active for "
                f"{self._owner}/{self._repo}. Lock: {self._lock_path}"
            )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None
