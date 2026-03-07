"""Trigger engine — evaluates trigger conditions and invokes the pipeline.

Supported trigger types (configured per-repo in ``PipelineConfig``):

- ``pr_merge``: fires when a PR is merged on GitHub.  Requires ``GH_TOKEN``
  in the environment; silently skipped when absent.
- ``daily``: fires once per calendar day (UTC).
- ``manual``: never fires automatically; use :meth:`TriggerEngine.fire_manual`.

The engine is stateful: it tracks the last daily-run date and the last
PR-check timestamp per repo across calls to :meth:`TriggerEngine.evaluate_repo`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Protocol

from pipeline.config.loader import PipelineConfig
from pipeline.trigger.github import has_merged_prs_since
from pipeline.trigger.schedule import is_daily_trigger_due

TRIGGER_PR_MERGE = "pr_merge"
TRIGGER_DAILY = "daily"
TRIGGER_MANUAL = "manual"

POLL_INTERVAL_SECONDS = 60


class PipelineRunner(Protocol):
    """Callable that executes the pipeline for a given repo and agent list."""

    def __call__(self, *, repo: str, agents: list[str]) -> None: ...


class TriggerEngine:
    """Evaluates per-repo trigger conditions and invokes the pipeline.

    The engine owns no I/O itself — it delegates GitHub checks to
    :func:`~pipeline.trigger.github.has_merged_prs_since` and schedule checks
    to :func:`~pipeline.trigger.schedule.is_daily_trigger_due`.  The
    *run_pipeline* callable is injected at construction time, keeping the
    engine independently testable.

    Args:
        config: Loaded pipeline configuration.
        run_pipeline: Called when a trigger fires.  Receives *repo* and
            *agents* as keyword arguments.
        clock: Optional callable that returns the current ``datetime``.
            Defaults to ``datetime.now(timezone.utc)``.  Pass a fixed
            callable in tests to control time.
    """

    def __init__(
        self,
        config: PipelineConfig,
        run_pipeline: PipelineRunner,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._run_pipeline = run_pipeline
        self._clock = clock or (lambda: datetime.now(UTC))
        # Date of last daily trigger fire per repo.
        self._last_daily_run: dict[str, date] = {}
        # Datetime of last PR-merge poll per repo.
        self._last_pr_check: dict[str, datetime] = {}

    def fire_manual(self, repo: str) -> None:
        """Immediately invoke the pipeline for *repo* (manual trigger).

        Args:
            repo: Repository slug in ``owner/repo`` format.

        Raises:
            ValueError: If *repo* is not present in the config, or if its
                trigger list does not include ``"manual"``.
        """
        repo_cfg = self._config.repos.get(repo)
        if repo_cfg is None:
            raise ValueError(f"Unknown repo: {repo!r}")
        if TRIGGER_MANUAL not in repo_cfg.triggers:
            raise ValueError(f"Repo {repo!r} does not have the 'manual' trigger enabled")
        self._run_pipeline(repo=repo, agents=repo_cfg.analysis_agents)

    def evaluate_repo(self, repo: str) -> bool:
        """Evaluate all trigger conditions for *repo* and fire if one is due.

        Iterates through the repo's configured triggers in order.  The first
        trigger that fires invokes the pipeline and stops evaluation (at most
        one pipeline run per call).  Internal timestamps are updated
        regardless of whether the pipeline ran.

        Args:
            repo: Repository slug in ``owner/repo`` format.

        Returns:
            ``True`` if the pipeline was invoked, ``False`` otherwise.
        """
        repo_cfg = self._config.repos.get(repo)
        if repo_cfg is None:
            return False

        now = self._clock()
        fired = False

        for trigger in repo_cfg.triggers:
            if trigger == TRIGGER_DAILY:
                last = self._last_daily_run.get(repo)
                if is_daily_trigger_due(last_run_date=last, now=now):
                    self._run_pipeline(repo=repo, agents=repo_cfg.analysis_agents)
                    self._last_daily_run[repo] = now.date()
                    fired = True
                    break

            elif trigger == TRIGGER_PR_MERGE:
                # Use now as `since` the very first time so we don't fire on
                # historical PRs that existed before the engine started.
                since = self._last_pr_check.get(repo, now)
                if has_merged_prs_since(repo=repo, since=since):
                    self._run_pipeline(repo=repo, agents=repo_cfg.analysis_agents)
                    fired = True
                    break

            # TRIGGER_MANUAL is intentionally not evaluated here; callers
            # invoke fire_manual() directly.

        # Always advance the PR-check cursor so the next evaluation only
        # looks at PRs merged after this point.
        if TRIGGER_PR_MERGE in repo_cfg.triggers:
            self._last_pr_check[repo] = now

        return fired

    def run_once(self) -> None:
        """Evaluate all configured repos exactly once."""
        for repo in self._config.repos:
            self.evaluate_repo(repo)

    def run_forever(self, poll_interval: float = POLL_INTERVAL_SECONDS) -> None:
        """Poll all repos continuously, sleeping between passes.

        Calls :meth:`run_once` then sleeps *poll_interval* seconds,
        repeating until the process is terminated.  Designed to run in a
        background thread or subprocess.

        Args:
            poll_interval: Seconds to sleep between evaluation passes.
                Defaults to :data:`POLL_INTERVAL_SECONDS` (60).
        """
        while True:
            self.run_once()
            time.sleep(poll_interval)
