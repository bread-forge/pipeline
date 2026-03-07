"""pipeline status subcommand — dashboard view of active cycles and proposals per repo."""

from __future__ import annotations

from pathlib import Path

import typer
from beads.store import BeadStore
from beads.types import CycleBead

from pipeline.store import BEADS_DIR, get_store, list_proposals

app = typer.Typer(help="Show pipeline status for a repository.")

# Phases that indicate a cycle is still in flight.
_ACTIVE_PHASES = frozenset({"analysis", "synthesis", "gate", "execution", "verification"})


def _parse_repo(repo: str) -> tuple[str, str]:
    """Split 'owner/repo' into (owner, name), exiting on bad input."""
    parts = repo.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        typer.echo(f"Error: --repo must be in 'owner/repo' format, got: {repo!r}", err=True)
        raise typer.Exit(code=1)
    return parts[0], parts[1]


def _load_all_cycles(
    store: BeadStore,
    beads_dir: Path,
    owner: str,
    repo_name: str,
) -> list[CycleBead]:
    """Return all cycle beads for a repo, sorted oldest-first by started_at.

    Scans the cycles directory for JSON files and loads each one through the
    BeadStore API to keep deserialization logic in one place.

    Args:
        store: BeadStore scoped to this repo (used for deserialization).
        beads_dir: Root bead storage directory (injectable for tests).
        owner: Repository owner name.
        repo_name: Repository name.

    Returns:
        All persisted CycleBeads sorted by ``started_at`` ascending, or an
        empty list when no cycles directory exists yet.
    """
    cycles_dir = beads_dir / owner / repo_name / "cycles"
    if not cycles_dir.exists():
        return []
    cycles: list[CycleBead] = []
    for path in cycles_dir.glob("*.json"):
        cycle = store.read_cycle(path.stem)
        if cycle is not None:
            cycles.append(cycle)
    return sorted(cycles, key=lambda c: c.started_at)


@app.callback(invoke_without_command=True)
def status(
    ctx: typer.Context,
    repo: str = typer.Option(..., "--repo", help="Repository in 'owner/repo' format."),
) -> None:
    """Print active cycles, pending proposals, suppression counts, and last cycle outcome."""
    if ctx.invoked_subcommand is not None:
        return

    owner, repo_name = _parse_repo(repo)
    store = get_store(repo)

    cycles = _load_all_cycles(store, BEADS_DIR, owner, repo_name)
    active_count = sum(1 for c in cycles if c.phase in _ACTIVE_PHASES)
    last_cycle = cycles[-1] if cycles else None

    proposals = list_proposals(store, repo)
    pending_count = sum(1 for p in proposals if p.status == "pending")

    suppressions = store.list_active_suppressions(repo=repo)
    active_suppressions = [s for s in suppressions if s.is_active()]

    typer.echo(f"repo:               {repo}")
    typer.echo(f"active_cycles:      {active_count}")
    typer.echo(f"pending_proposals:  {pending_count}")
    typer.echo(f"suppressions:       {len(active_suppressions)}")
    typer.echo(f"last_cycle_outcome: {last_cycle.phase if last_cycle else 'none'}")
