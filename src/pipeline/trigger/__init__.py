"""pipeline.trigger — trigger evaluation for the pipeline orchestrator.

Submodules
----------
engine
    :class:`~pipeline.trigger.engine.TriggerEngine` — orchestrates trigger
    evaluation and pipeline invocation.
github
    GitHub REST API poller for ``pr_merge`` triggers.
schedule
    Daily schedule check for ``daily`` triggers.
"""

from pipeline.trigger.engine import (
    POLL_INTERVAL_SECONDS,
    TRIGGER_DAILY,
    TRIGGER_MANUAL,
    TRIGGER_PR_MERGE,
    PipelineRunner,
    TriggerEngine,
)

__all__ = [
    "PipelineRunner",
    "POLL_INTERVAL_SECONDS",
    "TRIGGER_DAILY",
    "TRIGGER_MANUAL",
    "TRIGGER_PR_MERGE",
    "TriggerEngine",
]
