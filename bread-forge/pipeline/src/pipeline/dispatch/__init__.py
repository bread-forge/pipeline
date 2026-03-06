"""pipeline.dispatch — agent dispatching for the ANALYSIS phase.

Exports :class:`AgentDispatcher`, which runs ``repo-audit`` subprocesses,
records lifecycle events, and advances the cycle bead from ANALYSIS to
SYNTHESIS once all agents have reported completion.
"""

from pipeline.dispatch.agent import AgentDispatcher, AgentDispatchError

__all__ = ["AgentDispatchError", "AgentDispatcher"]
