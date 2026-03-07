"""pipeline watch command — poll for trigger events and invoke the pipeline.

Starts a :class:`~pipeline.trigger.TriggerEngine` polling loop for a single
repository.  The ``--on`` option selects which trigger type to register
(``pr_merge``, ``daily``, or ``manual``).  Each time the engine fires, it
dispatches the repo's configured analysis agents via
:class:`~pipeline.dispatch.AgentDispatcher` and prints a brief summary.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import typer
from beads.types import CycleBead

from pipeline.config.loader import PipelineConfig, RepoConfig, load_config
from pipeline.cycle.phase import CyclePhase
from pipeline.dispatch import AgentDispatcher, AgentDispatchError
from pipeline.events.log import EventLog
from pipeline.store import get_store, write_cycle
from pipeline.trigger import (
    TRIGGER_DAILY,
    TRIGGER_MANUAL,
    TRIGGER_PR_MERGE,
    TriggerEngine,
)

app = typer.Typer(help="Watch for trigger events and invoke the pipeline.")

VALID_TRIGGER_EVENTS: frozenset[str] = frozenset({TRIGGER_PR_MERGE, TRIGGER_DAILY, TRIGGER_MANUAL})


def _parse_repo(repo: str) -> tuple[str, str]:
    """Split 'owner/repo' into (owner, name), exiting on bad input."""
    parts = repo.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        typer.echo(f"Error: --repo must be in 'owner/repo' format, got: {repo!r}", err=True)
        raise typer.Exit(code=1)
    return parts[0], parts[1]


def _ensure_trigger_in_config(
    config: PipelineConfig,
    repo: str,
    trigger_event: str,
) -> None:
    """Add *trigger_event* to *repo* in *config* if not already present.

    Mutates *config.repos* in place so the caller's TriggerEngine sees the
    updated trigger list without needing to reload from disk.

    Args:
        config: The loaded pipeline configuration to mutate.
        repo: Repository slug in ``owner/repo`` format.
        trigger_event: The trigger type to register (e.g. ``"pr_merge"``).
    """
    if repo not in config.repos:
        config.repos[repo] = RepoConfig(triggers=[trigger_event])
    elif trigger_event not in config.repos[repo].triggers:
        # Prepend so the new trigger is evaluated first.
        config.repos[repo].triggers.insert(0, trigger_event)


def _build_pipeline_runner(owner: str, repo_name: str):  # type: ignore[return]
    """Return a PipelineRunner callback that dispatches agents and prints results.

    The returned callable matches the :class:`~pipeline.trigger.PipelineRunner`
    protocol: it receives *repo* and *agents* as keyword arguments, creates a
    fresh cycle, runs the dispatcher, and echoes a one-line summary.  Errors
    from individual agent subprocesses are caught and printed without crashing
    the polling loop.

    Args:
        owner: Repository owner (first segment of ``owner/repo``).
        repo_name: Repository name (second segment of ``owner/repo``).

    Returns:
        A callable compatible with :class:`~pipeline.trigger.PipelineRunner`.
    """

    def run_pipeline(*, repo: str, agents: list[str]) -> None:
        cycle_id = str(uuid.uuid4())
        store = get_store(repo)
        event_log = EventLog(owner, repo_name, cycle_id)

        bead = CycleBead(cycle_id=cycle_id, repo=repo, phase=CyclePhase.ANALYSIS)
        write_cycle(store, bead)

        dispatcher = AgentDispatcher(
            cycle_id=cycle_id,
            repo=repo,
            store=store,
            event_log=event_log,
        )

        try:
            findings = dispatcher.dispatch(agents, Path(".").resolve(), bead)
        except AgentDispatchError as exc:
            typer.echo(f"[watch] dispatch error for {repo!r}: {exc}", err=True)
            return

        typer.echo(f"[watch] pipeline triggered for {repo!r}: {len(findings)} finding(s).")

    return run_pipeline


@app.command()
def watch(
    repo: str = typer.Option(..., "--repo", help="Repository in 'owner/repo' format."),
    on: str = typer.Option(
        ...,
        "--on",
        help=f"Trigger event to watch: {', '.join(sorted(VALID_TRIGGER_EVENTS))}.",
    ),
    poll_interval: float = typer.Option(
        60.0,
        "--interval",
        help="Seconds between polling passes. Defaults to 60.",
    ),
) -> None:
    """Start a polling loop that fires the pipeline when *on* event occurs.

    Loads the pipeline config, registers the requested trigger for *repo*,
    then calls :meth:`~pipeline.trigger.TriggerEngine.run_forever`.  Press
    Ctrl-C to stop.
    """
    owner, repo_name = _parse_repo(repo)

    if on not in VALID_TRIGGER_EVENTS:
        valid = ", ".join(sorted(VALID_TRIGGER_EVENTS))
        typer.echo(f"Error: unknown event {on!r}. Valid events: {valid}.", err=True)
        raise typer.Exit(code=1)

    config = load_config()
    _ensure_trigger_in_config(config, repo, on)

    run_pipeline = _build_pipeline_runner(owner, repo_name)
    engine = TriggerEngine(config=config, run_pipeline=run_pipeline)

    typer.echo(
        f"Watching {repo!r} for {on!r} events "
        f"(poll_interval={poll_interval}s). Press Ctrl-C to stop."
    )
    try:
        engine.run_forever(poll_interval=poll_interval)
    except KeyboardInterrupt:
        typer.echo("\nWatch stopped.")
