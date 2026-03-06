"""pipeline suppressions subcommands: list, expire."""

from __future__ import annotations

from datetime import UTC, datetime

import typer

from pipeline.store import get_store

app = typer.Typer(help="Manage pipeline suppressions.")

_COL_ID = 36
_COL_CLASS = 30
_COL_DECISION = 10
_COL_REASON = 40

_HEADER = (
    f"{'ID':<{_COL_ID}}  {'FINDING_CLASS':<{_COL_CLASS}}  "
    f"{'DECISION':<{_COL_DECISION}}  {'REASON':<{_COL_REASON}}  EXPIRES_AT"
)
_SEPARATOR = "-" * (len(_HEADER) + 10)


@app.command("list")
def list_suppressions(
    repo: str = typer.Option(..., "--repo", help="Repository in 'owner/repo' format."),
) -> None:
    """List active suppressions for a repository in tabular form."""
    store = get_store(repo)
    suppressions = store.list_active_suppressions(repo=repo)

    if not suppressions:
        typer.echo("No active suppressions.")
        return

    typer.echo(_HEADER)
    typer.echo(_SEPARATOR)
    for s in suppressions:
        expires = s.expires_at.isoformat() if s.expires_at else "never"
        typer.echo(
            f"{s.suppression_id:<{_COL_ID}}  {s.finding_class:<{_COL_CLASS}}  "
            f"{s.decision:<{_COL_DECISION}}  {s.reason:<{_COL_REASON}}  {expires}"
        )


@app.command()
def expire(
    suppression_id: str = typer.Argument(..., help="Suppression ID to expire immediately."),
    repo: str = typer.Option(..., "--repo", help="Repository in 'owner/repo' format."),
) -> None:
    """Expire a suppression immediately by setting its expires_at to now."""
    store = get_store(repo)
    suppression = store.read_suppression(suppression_id)

    if suppression is None:
        typer.echo(f"Error: No suppression found with id {suppression_id!r}", err=True)
        raise typer.Exit(code=1)

    updated = suppression.model_copy(update={"expires_at": datetime.now(UTC)})
    store.write_suppression(updated)
    typer.echo(f"Suppression {suppression_id!r} expired.")
