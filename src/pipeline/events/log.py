"""EventLog: append-only JSONL event store with typed replay."""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from pathlib import Path

from pipeline.events.types import EVENT_REGISTRY, AnyEvent


def _serialize(event: AnyEvent) -> str:
    """Serialize an event to a JSON string.

    Converts the dataclass to a dict and ISO-formats the timestamp so it
    round-trips cleanly through JSON without a custom encoder.
    """
    d = dataclasses.asdict(event)
    d["timestamp"] = event.timestamp.isoformat()  # type: ignore[union-attr]
    return json.dumps(d)


def _deserialize(line: str) -> AnyEvent:
    """Deserialize a JSON line back to a typed event dataclass.

    Raises KeyError if event_type is not in the registry (unknown event).
    Raises ValueError if the JSON is malformed.
    """
    d = json.loads(line)
    event_type = d.pop("event_type")
    cls = EVENT_REGISTRY[event_type]
    d["timestamp"] = datetime.fromisoformat(d["timestamp"])
    return cls(**d)  # type: ignore[return-value]


class EventLog:
    """Append-only event log backed by a JSONL file.

    Each cycle gets its own file at:
        <base_dir>/events/<owner>-<repo>/<cycle-id>.jsonl

    Pass ``base_dir`` explicitly in tests to avoid writing to ~/.pipeline.
    """

    def __init__(
        self,
        owner: str,
        repo: str,
        cycle_id: str,
        base_dir: Path | None = None,
    ) -> None:
        if base_dir is None:
            base_dir = Path.home() / ".pipeline"
        self._path = base_dir / "events" / f"{owner}-{repo}" / f"{cycle_id}.jsonl"

    @property
    def path(self) -> Path:
        """The JSONL file path for this cycle's event log."""
        return self._path

    def append(self, event: AnyEvent) -> None:
        """Serialize and append a single event to the JSONL file.

        Creates the parent directory on first write.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a") as fh:
            fh.write(_serialize(event) + "\n")

    def replay(self) -> list[AnyEvent]:
        """Read the JSONL file and return all events in order.

        Returns an empty list if the log file does not yet exist.
        Raises KeyError for unknown event_type values encountered in the file.
        """
        if not self._path.exists():
            return []
        events: list[AnyEvent] = []
        with self._path.open() as fh:
            for line in fh:
                stripped = line.strip()
                if stripped:
                    events.append(_deserialize(stripped))
        return events
