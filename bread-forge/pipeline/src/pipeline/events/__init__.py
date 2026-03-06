"""Pipeline events module.

Exports typed event dataclasses, the AnyEvent union, and EventLog.
"""

from pipeline.events.log import EventLog
from pipeline.events.types import (
    EVENT_REGISTRY,
    AgentCompleted,
    AgentDispatched,
    AnyEvent,
    CycleCompleted,
    CycleStarted,
    ExecutionStarted,
    GateDecision,
    ProposalSubmitted,
    SynthesisStarted,
    VerificationVerdict,
)

__all__ = [
    "AgentCompleted",
    "AgentDispatched",
    "AnyEvent",
    "CycleCompleted",
    "CycleStarted",
    "EVENT_REGISTRY",
    "EventLog",
    "ExecutionStarted",
    "GateDecision",
    "ProposalSubmitted",
    "SynthesisStarted",
    "VerificationVerdict",
]
