"""Typed event dataclasses for the pipeline event log."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class CycleStarted:
    """Emitted when a new pipeline cycle begins."""

    cycle_id: str
    timestamp: datetime
    owner: str
    repo: str
    event_type: str = field(default="CycleStarted", init=False)


@dataclass(frozen=True)
class AgentDispatched:
    """Emitted when a sub-agent is dispatched to work on an issue."""

    cycle_id: str
    timestamp: datetime
    issue_number: int
    branch: str
    event_type: str = field(default="AgentDispatched", init=False)


@dataclass(frozen=True)
class AgentCompleted:
    """Emitted when a sub-agent finishes its work."""

    cycle_id: str
    timestamp: datetime
    issue_number: int
    success: bool
    pr_number: int | None = None
    event_type: str = field(default="AgentCompleted", init=False)


@dataclass(frozen=True)
class SynthesisStarted:
    """Emitted when the synthesis phase begins after all agents complete."""

    cycle_id: str
    timestamp: datetime
    event_type: str = field(default="SynthesisStarted", init=False)


@dataclass(frozen=True)
class ProposalSubmitted:
    """Emitted when a synthesized proposal is ready for gate review."""

    cycle_id: str
    timestamp: datetime
    proposal_id: str
    event_type: str = field(default="ProposalSubmitted", init=False)


@dataclass(frozen=True)
class GateDecision:
    """Emitted when the gate approves or rejects a proposal."""

    cycle_id: str
    timestamp: datetime
    approved: bool
    reason: str
    event_type: str = field(default="GateDecision", init=False)


@dataclass(frozen=True)
class ExecutionStarted:
    """Emitted when approved changes begin executing."""

    cycle_id: str
    timestamp: datetime
    proposal_id: str
    event_type: str = field(default="ExecutionStarted", init=False)


@dataclass(frozen=True)
class VerificationVerdict:
    """Emitted when post-execution verification completes."""

    cycle_id: str
    timestamp: datetime
    passed: bool
    details: str
    event_type: str = field(default="VerificationVerdict", init=False)


@dataclass(frozen=True)
class CycleCompleted:
    """Emitted when the pipeline cycle closes."""

    cycle_id: str
    timestamp: datetime
    outcome: str
    event_type: str = field(default="CycleCompleted", init=False)


@dataclass
class BudgetExceeded(Exception):
    """Raised and emitted when accumulated agent costs exceed the cycle budget cap."""

    cycle_id: str
    timestamp: datetime
    agent_id: str
    total_usd: float
    limit_usd: float
    event_type: str = field(default="BudgetExceeded", init=False)


# Union of all event types — used for type annotations throughout the pipeline.
AnyEvent = (
    CycleStarted
    | AgentDispatched
    | AgentCompleted
    | SynthesisStarted
    | ProposalSubmitted
    | GateDecision
    | ExecutionStarted
    | VerificationVerdict
    | CycleCompleted
    | BudgetExceeded
)

# Maps event_type string → dataclass constructor. Used by EventLog.replay().
EVENT_REGISTRY: dict[str, type] = {
    "CycleStarted": CycleStarted,
    "AgentDispatched": AgentDispatched,
    "AgentCompleted": AgentCompleted,
    "SynthesisStarted": SynthesisStarted,
    "ProposalSubmitted": ProposalSubmitted,
    "GateDecision": GateDecision,
    "ExecutionStarted": ExecutionStarted,
    "VerificationVerdict": VerificationVerdict,
    "CycleCompleted": CycleCompleted,
    "BudgetExceeded": BudgetExceeded,
}
