"""AgentDispatcher — run repo-audit agents and transition ANALYSIS → SYNTHESIS.

Each agent is launched as a subprocess running ``repo-audit run <repo-path>``.
After all agents finish, the dispatcher reads :class:`~beads.types.FindingBead`
objects from the :class:`~beads.store.BeadStore`, then uses
:class:`~pipeline.cycle.state_machine.CycleStateMachine` to advance the cycle
from ANALYSIS to SYNTHESIS and persists the new phase to the store.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from beads.store import BeadStore
from beads.types import CycleBead, FindingBead

from pipeline.budget.tracker import BudgetTracker
from pipeline.cycle.bead import write_phase_transition
from pipeline.cycle.state_machine import CycleEvent, CycleStateMachine
from pipeline.events.log import EventLog
from pipeline.events.types import AgentCompleted, AgentDispatched, BudgetExceeded

__all__ = ["AgentDispatchError", "AgentDispatcher"]

# Sentinel used for issue_number in audit-agent events (no GitHub issue context).
_AUDIT_ISSUE_NUMBER: int = 0


class AgentDispatchError(Exception):
    """Raised when a repo-audit subprocess exits with a non-zero status."""


class AgentDispatcher:
    """Run named repo-audit agents and advance the cycle to SYNTHESIS when done.

    Usage::

        dispatcher = AgentDispatcher(
            cycle_id="abc123",
            repo="owner/repo",
            store=store,
            event_log=event_log,
        )
        findings = dispatcher.dispatch(["depth", "coverage"], repo_path)

    The dispatcher emits :class:`~pipeline.events.types.AgentDispatched` before
    launching each subprocess and :class:`~pipeline.events.types.AgentCompleted`
    after it exits.  Once all agents have run it emits a synthetic
    ``all_agents_completed`` :class:`~pipeline.cycle.state_machine.CycleEvent`
    to satisfy the ANALYSIS completion criteria in
    :class:`~pipeline.cycle.state_machine.CycleStateMachine`, then persists
    the SYNTHESIS phase to the bead store.
    """

    def __init__(
        self,
        cycle_id: str,
        repo: str,
        store: BeadStore,
        event_log: EventLog,
        state_machine: CycleStateMachine | None = None,
        budget_tracker: BudgetTracker | None = None,
    ) -> None:
        self._cycle_id = cycle_id
        self._repo = repo
        self._store = store
        self._event_log = event_log
        self._sm = state_machine if state_machine is not None else CycleStateMachine()
        self._budget_tracker = budget_tracker

    def dispatch(
        self,
        agent_names: Sequence[str],
        repo_path: Path,
        bead: CycleBead,
    ) -> list[FindingBead]:
        """Run all agents, emit events, and advance the cycle to SYNTHESIS.

        Agents are run sequentially in the order given.  If any agent process
        exits with a non-zero return code an :class:`AgentDispatchError` is
        raised immediately — subsequent agents are not started.  When a
        :class:`~pipeline.budget.tracker.BudgetTracker` is configured, cost is
        recorded after each successful agent; if the running total exceeds the
        cap a :class:`~pipeline.events.types.BudgetExceeded` event is emitted
        to the event log and remaining agents are skipped.

        Args:
            agent_names: Ordered sequence of agent identifiers to run.  Each
                name is passed to the subprocess as the ``REPO_AUDIT_AGENT``
                environment variable and recorded in the dispatched/completed
                events.
            repo_path: Absolute path to the repository to audit.
            bead: The current :class:`~beads.types.CycleBead`.  Its ``phase``
                field is updated in-place and written to the store on success.

        Returns:
            All :class:`~beads.types.FindingBead` objects for this cycle that
            are present in the store after agents complete.

        Raises:
            AgentDispatchError: When a repo-audit subprocess exits non-zero.
            InvalidPhaseTransitionError: When the state machine cannot advance
                (e.g. the bead is not in ANALYSIS phase).
        """
        for agent_name in agent_names:
            cost = self._run_one(agent_name, repo_path)
            if self._budget_tracker is not None:
                try:
                    self._budget_tracker.record_cost(agent_name, cost)
                except BudgetExceeded as exc:
                    self._event_log.append(exc)
                    break

        cycle_findings = self._collect_findings()
        next_phase = self._advance_to_synthesis(bead, cycle_findings)
        write_phase_transition(self._store, bead, next_phase)
        return cycle_findings

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_one(self, agent_name: str, repo_path: Path) -> float:
        """Launch a single repo-audit subprocess and emit lifecycle events.

        Args:
            agent_name: Logical name for this agent (used in events and env).
            repo_path: Path passed to ``repo-audit run``.

        Returns:
            The cost in USD reported by the agent via JSON stdout, or 0.0 if
            the agent did not report a cost.

        Raises:
            AgentDispatchError: When the subprocess exits with a non-zero code.
        """
        self._event_log.append(
            AgentDispatched(
                cycle_id=self._cycle_id,
                timestamp=datetime.now(UTC),
                # Audit agents have no corresponding GitHub issue; use sentinel.
                issue_number=_AUDIT_ISSUE_NUMBER,
                branch=agent_name,
            )
        )

        env = {**os.environ, "REPO_AUDIT_AGENT": agent_name}
        result = subprocess.run(
            ["repo-audit", "run", str(repo_path)],
            capture_output=True,
            text=True,
            env=env,
        )
        success = result.returncode == 0

        self._event_log.append(
            AgentCompleted(
                cycle_id=self._cycle_id,
                timestamp=datetime.now(UTC),
                issue_number=_AUDIT_ISSUE_NUMBER,
                success=success,
            )
        )

        if not success:
            raise AgentDispatchError(
                f"Agent {agent_name!r} exited with code {result.returncode}. "
                f"stderr: {result.stderr.strip()!r}"
            )

        return self._parse_agent_cost(result.stdout)

    @staticmethod
    def _parse_agent_cost(stdout: str) -> float:
        """Parse cost_usd from agent JSON stdout, returning 0.0 on failure.

        Agents may optionally report their LLM cost by writing a JSON object
        with a ``cost_usd`` key to stdout.  If the output is not valid JSON or
        lacks that key, zero cost is assumed — existing agents that produce no
        structured output are unaffected.
        """
        try:
            data = json.loads(stdout)
            cost = data.get("cost_usd", 0.0)
            return float(cost) if isinstance(cost, (int, float)) else 0.0
        except (json.JSONDecodeError, AttributeError, TypeError):
            return 0.0

    def _collect_findings(self) -> list[FindingBead]:
        """Return all findings for this cycle from the store.

        Reads every :class:`~beads.types.FindingBead` for ``self._repo`` and
        filters to those whose ``cycle_id`` matches the current cycle.
        """
        all_findings = self._store.list_findings(repo=self._repo)
        return [f for f in all_findings if f.cycle_id == self._cycle_id]

    def _advance_to_synthesis(
        self,
        bead: CycleBead,
        findings: list[FindingBead],
    ) -> object:
        """Build the CycleEvents needed to advance ANALYSIS and call the SM.

        One ``finding_added`` :class:`CycleEvent` is created for each finding
        in *findings*.  An ``all_agents_completed`` event is always appended so
        the transition succeeds even when no findings were produced.

        Args:
            bead: Current cycle bead.
            findings: Findings collected after agent runs.

        Returns:
            The successor :class:`~pipeline.cycle.phase.CyclePhase`.
        """
        cycle_events: list[CycleEvent] = [CycleEvent("finding_added") for _ in findings]
        cycle_events.append(CycleEvent("all_agents_completed"))
        return self._sm.advance(bead, cycle_events)
