"""pipeline run command — dispatch agents and print synthesis proposals.

Instantiates an :class:`~pipeline.dispatch.AgentDispatcher`, runs configured
or explicitly specified agents against the repository, waits for all agents to
complete, then prints a synthesis stub: a numbered proposal list derived from
the raw :class:`~beads.types.FindingBead` objects collected during analysis.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

import typer
from beads.types import CycleBead, FindingBead

from pipeline.budget.tracker import BudgetTracker
from pipeline.config.loader import load_config
from pipeline.cycle.phase import CyclePhase
from pipeline.dispatch import AgentDispatcher, AgentDispatchError
from pipeline.events.log import EventLog
from pipeline.store import get_store, write_cycle

app = typer.Typer(help="Dispatch agents against a repository and print synthesis proposals.")


def _parse_repo(repo: str) -> tuple[str, str]:
    """Split 'owner/repo' into (owner, name), exiting on bad input."""
    parts = repo.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        typer.echo(f"Error: --repo must be in 'owner/repo' format, got: {repo!r}", err=True)
        raise typer.Exit(code=1)
    return parts[0], parts[1]


def _resolve_agents(repo: str, agents: list[str] | None) -> list[str]:
    """Return the agent list to dispatch.

    Uses explicitly provided *agents* when given.  Falls back to the
    ``analysis_agents`` list from the loaded config for *repo*.  Returns an
    empty list when neither source provides agents (dispatch will still
    advance the cycle via ``all_agents_completed``).

    Args:
        repo: Repository slug in ``owner/repo`` format.
        agents: Agent names supplied on the command line, or ``None`` if the
            option was not passed.

    Returns:
        Ordered list of agent name strings.
    """
    if agents:
        return list(agents)
    config = load_config()
    repo_cfg = config.repos.get(repo)
    return repo_cfg.analysis_agents if repo_cfg else []


def _print_synthesis_stub(findings: list[FindingBead]) -> None:
    """Print a synthesis stub — a numbered proposal list from raw findings.

    Each finding becomes one proposal line showing severity, reasoning, the
    agent that produced it, and its confidence score.

    Args:
        findings: Findings collected by the dispatcher after agents complete.
    """
    if not findings:
        typer.echo("Synthesis: no findings — no proposals generated.")
        return

    typer.echo(f"Synthesis proposals ({len(findings)} finding(s)):")
    for i, finding in enumerate(findings, start=1):
        typer.echo(f"  {i}. [{finding.severity.upper()}] {finding.reasoning}")
        typer.echo(
            f"       agent={finding.agent!r}  "
            f"confidence={finding.confidence:.2f}  "
            f"class={finding.staleness_class}"
        )


@app.command()
def run(
    repo: str = typer.Option(..., "--repo", help="Repository in 'owner/repo' format."),
    agents: Annotated[
        list[str] | None,
        typer.Option(
            "--agents",
            help="Agent names to dispatch (repeatable: --agents a --agents b). "
            "Defaults to analysis_agents from config.",
        ),
    ] = None,
    repo_path: Annotated[
        Path,
        typer.Option(
            "--path", help="Local filesystem path to the repository root. Defaults to '.'."
        ),
    ] = Path("."),
    max_analysis_cost: Annotated[
        float | None,
        typer.Option(
            "--max-analysis-cost",
            help="Maximum USD cost for the analysis phase. "
            "Agents are skipped once this cap is exceeded.",
        ),
    ] = None,
) -> None:
    """Dispatch configured or specified agents and print a synthesis stub.

    Creates a fresh pipeline cycle in ANALYSIS phase, dispatches each agent as
    a ``repo-audit run`` subprocess, waits for all to complete, then prints a
    numbered list of proposals derived from the collected findings.
    """
    owner, repo_name = _parse_repo(repo)
    resolved_agents = _resolve_agents(repo, agents)

    cycle_id = str(uuid.uuid4())
    store = get_store(repo)
    event_log = EventLog(owner, repo_name, cycle_id)

    bead = CycleBead(cycle_id=cycle_id, repo=repo, phase=CyclePhase.ANALYSIS)
    write_cycle(store, bead)

    budget_tracker = (
        BudgetTracker(cycle_id=cycle_id, cap_usd=max_analysis_cost)
        if max_analysis_cost is not None
        else None
    )

    dispatcher = AgentDispatcher(
        cycle_id=cycle_id,
        repo=repo,
        store=store,
        event_log=event_log,
        budget_tracker=budget_tracker,
    )

    try:
        findings = dispatcher.dispatch(resolved_agents, repo_path.resolve(), bead)
    except AgentDispatchError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None

    _print_synthesis_stub(findings)
