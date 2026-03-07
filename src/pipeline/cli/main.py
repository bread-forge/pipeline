"""pipeline CLI entry point — registers all subcommand groups."""

import typer

from pipeline.cli.commands.cycle import app as cycle_app
from pipeline.cli.commands.gate import app as gate_app
from pipeline.cli.commands.run import app as run_app
from pipeline.cli.commands.status import app as status_app
from pipeline.cli.commands.suppressions import app as suppressions_app
from pipeline.cli.commands.telemetry import app as telemetry_app
from pipeline.cli.commands.watch import app as watch_app

app = typer.Typer(
    name="pipeline",
    help="Pipeline orchestrator CLI.",
    no_args_is_help=True,
)

app.add_typer(cycle_app, name="cycle")
app.add_typer(gate_app, name="gate")
app.add_typer(run_app, name="run")
app.add_typer(status_app, name="status")
app.add_typer(suppressions_app, name="suppressions")
app.add_typer(telemetry_app, name="telemetry")
app.add_typer(watch_app, name="watch")


def main() -> None:
    app()
