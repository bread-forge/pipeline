"""pipeline CLI entry point — registers all subcommand groups."""

import typer

from pipeline.cli.commands.cycle import app as cycle_app
from pipeline.cli.commands.run import app as run_app
from pipeline.cli.commands.watch import app as watch_app

app = typer.Typer(
    name="pipeline",
    help="Pipeline orchestrator CLI.",
    no_args_is_help=True,
)

app.add_typer(cycle_app, name="cycle")
app.add_typer(run_app, name="run")
app.add_typer(watch_app, name="watch")


def main() -> None:
    app()
