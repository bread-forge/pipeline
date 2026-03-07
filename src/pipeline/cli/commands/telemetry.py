"""pipeline telemetry subcommand — tabular view of recent per-cycle telemetry records."""

from __future__ import annotations

from typing import Annotated

import typer

from pipeline.telemetry.store import TelemetryStore

app = typer.Typer(help="Show telemetry records for a repository.")

DEFAULT_LAST_N: int = 10

_COL_DATE: int = 25
_COL_PROPOSALS: int = 9
_COL_APPROVED: int = 9
_COL_REJECTED: int = 9
_COL_COST: int = 10

_HEADER = (
    f"{'DATE':<{_COL_DATE}}  {'PROPOSALS':>{_COL_PROPOSALS}}  "
    f"{'APPROVED%':>{_COL_APPROVED}}  {'REJECTED%':>{_COL_REJECTED}}  "
    f"{'COST (USD)':>{_COL_COST}}"
)
_SEPARATOR = "-" * len(_HEADER)


def _parse_repo(repo: str) -> tuple[str, str]:
    """Split 'owner/repo' into (owner, name), exiting on bad input."""
    parts = repo.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        typer.echo(f"Error: --repo must be in 'owner/repo' format, got: {repo!r}", err=True)
        raise typer.Exit(code=1)
    return parts[0], parts[1]


def _format_row(rec: dict) -> str:  # type: ignore[type-arg]
    """Format a single telemetry record as a fixed-width table row.

    Args:
        rec: A dict with at least the keys ``date``, ``proposal_count``,
            ``approved_rate``, ``rejected_rate``, and ``total_cost_usd``.

    Returns:
        A single formatted string with columns aligned to the header widths.
    """
    date = str(rec.get("date", ""))
    proposals = int(rec.get("proposal_count", 0))
    approved_pct = float(rec.get("approved_rate", 0.0)) * 100
    rejected_pct = float(rec.get("rejected_rate", 0.0)) * 100
    cost = float(rec.get("total_cost_usd", 0.0))
    return (
        f"{date:<{_COL_DATE}}  {proposals:>{_COL_PROPOSALS}}  "
        f"{approved_pct:>{_COL_APPROVED - 1}.1f}%  "
        f"{rejected_pct:>{_COL_REJECTED - 1}.1f}%  "
        f"{cost:>{_COL_COST}.4f}"
    )


@app.callback(invoke_without_command=True)
def telemetry(
    ctx: typer.Context,
    repo: str = typer.Option(..., "--repo", help="Repository in 'owner/repo' format."),
    last: Annotated[
        int,
        typer.Option("--last", help="Number of most-recent records to display."),
    ] = DEFAULT_LAST_N,
) -> None:
    """Print a tabular view of the last N telemetry records for a repository."""
    if ctx.invoked_subcommand is not None:
        return

    owner, repo_name = _parse_repo(repo)
    store = TelemetryStore(owner, repo_name)
    records = store.read_all()[-last:]

    if not records:
        typer.echo("No telemetry records found.")
        return

    typer.echo(_HEADER)
    typer.echo(_SEPARATOR)
    for rec in records:
        typer.echo(_format_row(rec))
