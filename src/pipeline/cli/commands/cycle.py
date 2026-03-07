"""pipeline cycle subcommands: start, status, replay."""

from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import typer
from beads.types import CycleBead

from pipeline.lock import LockAcquisitionError, OrchestratorLock
from pipeline.store import get_store, write_cycle

app = typer.Typer(help="Manage pipeline cycles.")

# Default directory for per-cycle JSONL event logs.
EVENTS_DIR: Path = Path.home() / ".pipeline" / "events"


def _parse_repo(repo: str) -> tuple[str, str]:
    """Split 'owner/repo' into (owner, name), exiting on bad input."""
    parts = repo.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        typer.echo(f"Error: --repo must be in 'owner/repo' format, got: {repo!r}", err=True)
        raise typer.Exit(code=1)
    return parts[0], parts[1]


def _event_log_path(owner: str, repo_name: str, cycle_id: str) -> Path:
    """Return path to the JSONL event log for a given cycle."""
    return EVENTS_DIR / owner / repo_name / f"{cycle_id}.jsonl"


def _append_event(log_path: Path, event: dict) -> None:
    """Append a single JSON event line to the event log, creating it if needed."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def _read_events(log_path: Path) -> list[dict]:
    """Read all events from a JSONL event log.

    Returns an empty list when the log file does not exist.
    Skips blank lines silently.
    """
    if not log_path.exists():
        return []
    events = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            events.append(json.loads(stripped))
    return events


@app.command()
def start(
    repo: str = typer.Option(..., "--repo", help="Repository in 'owner/repo' format."),
    trigger: str | None = typer.Option(
        None, "--trigger", help="Optional free-text description of what triggered this cycle."
    ),
) -> None:
    """Start a new pipeline cycle.

    Acquires the orchestrator lock, generates a cycle ID, writes the initial
    CycleBead, emits a cycle_started event to the JSONL log, and prints the
    cycle ID to stdout.
    """
    owner, repo_name = _parse_repo(repo)

    try:
        with OrchestratorLock(owner, repo_name):
            cycle_id = str(uuid.uuid4())
            store = get_store(repo)
            bead = CycleBead(cycle_id=cycle_id, repo=repo, trigger=trigger)
            write_cycle(store, bead)

            log_path = _event_log_path(owner, repo_name, cycle_id)
            _append_event(
                log_path,
                {
                    "event_type": "cycle_started",
                    "cycle_id": cycle_id,
                    "repo": repo,
                    "phase": bead.phase,
                    "trigger": trigger,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )

            typer.echo(cycle_id)

    except LockAcquisitionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None


@app.command()
def status(
    cycle_id: str = typer.Argument(..., help="Cycle ID to query."),
    repo: str = typer.Option(..., "--repo", help="Repository in 'owner/repo' format."),
) -> None:
    """Show current phase and event summary for a cycle."""
    owner, repo_name = _parse_repo(repo)
    store = get_store(repo)
    bead = store.read_cycle(cycle_id)

    if bead is None:
        typer.echo(f"Error: No cycle found with id {cycle_id!r}", err=True)
        raise typer.Exit(code=1)

    log_path = _event_log_path(owner, repo_name, cycle_id)
    events = _read_events(log_path)
    counts: Counter[str] = Counter(e.get("event_type", "unknown") for e in events)

    typer.echo(f"cycle_id: {bead.cycle_id}")
    typer.echo(f"repo:     {bead.repo}")
    typer.echo(f"phase:    {bead.phase}")
    typer.echo(f"started:  {bead.started_at.isoformat()}")
    typer.echo(f"events:   {len(events)} total")
    for event_type, count in sorted(counts.items()):
        typer.echo(f"  {event_type}: {count}")


@app.command()
def replay(
    cycle_id: str = typer.Argument(..., help="Cycle ID whose events to print."),
    repo: str = typer.Option(..., "--repo", help="Repository in 'owner/repo' format."),
) -> None:
    """Print all events from the JSONL log for a cycle, one JSON object per line."""
    owner, repo_name = _parse_repo(repo)
    log_path = _event_log_path(owner, repo_name, cycle_id)
    events = _read_events(log_path)

    if not events:
        typer.echo(f"No events found for cycle {cycle_id!r}", err=True)
        raise typer.Exit(code=1)

    for event in events:
        typer.echo(json.dumps(event))
