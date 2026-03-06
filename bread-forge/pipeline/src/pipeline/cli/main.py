"""pipeline CLI entry point — registers all subcommand groups."""

import typer

from pipeline.cli.commands.cycle import app as cycle_app

app = typer.Typer(
    name="pipeline",
    help="Pipeline orchestrator CLI.",
    no_args_is_help=True,
)

app.add_typer(cycle_app, name="cycle")


def main() -> None:
    app()
