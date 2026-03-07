"""pipeline gate command — review and act on pending proposals in a TUI.

Resolves pending :class:`~beads.types.ProposalBead` objects from the
BeadStore for the given repository, optionally filtering by cycle ID, then
launches :class:`~pipeline.gate.app.GateApp` wired to the store and an
optional :class:`~pipeline.events.log.EventLog`.
"""

from __future__ import annotations

from typing import Annotated

import typer
from beads.types import ProposalBead

from pipeline.events.log import EventLog
from pipeline.store import get_store, list_proposals

app = typer.Typer(help="Review and act on pending gate proposals in a TUI.")


def _parse_repo(repo: str) -> tuple[str, str]:
    """Split 'owner/repo' into (owner, name), exiting on bad input."""
    parts = repo.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        typer.echo(f"Error: --repo must be in 'owner/repo' format, got: {repo!r}", err=True)
        raise typer.Exit(code=1)
    return parts[0], parts[1]


def _filter_pending(proposals: list[ProposalBead]) -> list[ProposalBead]:
    """Return only proposals whose status is 'pending'."""
    return [p for p in proposals if p.status == "pending"]


@app.command()
def gate(
    repo: str = typer.Option(..., "--repo", help="Repository in 'owner/repo' format."),
    cycle: str | None = typer.Option(
        None,
        "--cycle",
        help="Cycle ID to restrict proposals to. Defaults to all cycles.",
    ),
    headless_test: Annotated[
        bool,
        typer.Option(
            "--headless-test",
            hidden=True,
            help="Exit automatically after a short delay. For CI smoke tests only.",
        ),
    ] = False,
) -> None:
    """Launch the gate TUI to review and act on pending proposals.

    Loads pending proposals from the BeadStore for *repo*, optionally
    filtered to a single *cycle*, then opens the interactive TUI.  When no
    pending proposals exist the command prints a message and exits cleanly.
    """
    owner, repo_name = _parse_repo(repo)
    store = get_store(repo)

    proposals = list_proposals(store, repo, cycle_id=cycle)
    pending = _filter_pending(proposals)

    if not pending:
        typer.echo("No pending proposals found.")
        return

    event_log: EventLog | None = None
    if cycle is not None:
        event_log = EventLog(owner, repo_name, cycle)

    # Deferred import: textual is an optional heavy dependency; importing it at
    # module level would break test collection in environments without it.
    from pipeline.gate.app import GateApp  # noqa: PLC0415

    gate_app = GateApp(
        proposals=pending,
        store=store,
        event_log=event_log,
        headless_test=headless_test,
    )
    gate_app.run()
