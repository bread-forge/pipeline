"""TelemetryStore: append-only JSONL record store for per-cycle telemetry."""

from __future__ import annotations

import json
from pathlib import Path


class TelemetryStore:
    """Appends one JSONL record per completed cycle to a per-repo telemetry file.

    Records land at::

        <base_dir>/telemetry/{owner}-{repo}.jsonl

    Pass ``base_dir`` explicitly in tests to avoid writing to ``~/.pipeline``.
    """

    def __init__(
        self,
        owner: str,
        repo: str,
        base_dir: Path | None = None,
    ) -> None:
        if base_dir is None:
            base_dir = Path.home() / ".pipeline"
        self._path = base_dir / "telemetry" / f"{owner}-{repo}.jsonl"

    @property
    def path(self) -> Path:
        """The JSONL file path for this repo's telemetry."""
        return self._path

    def append(self, record: dict) -> None:  # type: ignore[type-arg]
        """Serialize and append *record* as a single JSON line.

        Creates the parent directory on first write.

        Args:
            record: Any JSON-serialisable dict representing one cycle's telemetry.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a") as fh:
            fh.write(json.dumps(record) + "\n")

    def read_all(self) -> list[dict]:  # type: ignore[type-arg]
        """Return all records from the telemetry file in order.

        Returns an empty list if the file does not yet exist.
        Blank lines in the file are silently skipped.
        """
        if not self._path.exists():
            return []
        records: list[dict] = []  # type: ignore[type-arg]
        with self._path.open() as fh:
            for line in fh:
                stripped = line.strip()
                if stripped:
                    records.append(json.loads(stripped))
        return records
