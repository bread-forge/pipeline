"""Tests for the trigger module — PR-merge detection, daily schedule, and TriggerEngine."""

from __future__ import annotations

import json
import urllib.error
from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest

from pipeline.config.loader import PipelineConfig, RepoConfig
from pipeline.trigger.engine import (
    TRIGGER_DAILY,
    TRIGGER_MANUAL,
    TRIGGER_PR_MERGE,
    TriggerEngine,
)
from pipeline.trigger.github import fetch_merged_prs, has_merged_prs_since
from pipeline.trigger.schedule import is_daily_trigger_due

# ---------------------------------------------------------------------------
# is_daily_trigger_due — pure schedule logic
# ---------------------------------------------------------------------------


class TestIsDailyTriggerDue:
    """Tests for is_daily_trigger_due()."""

    def test_returns_true_when_never_run(self) -> None:
        """None last_run_date means the pipeline has never fired — due immediately."""
        now = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        assert is_daily_trigger_due(last_run_date=None, now=now) is True

    def test_returns_false_when_already_run_today(self) -> None:
        """If last_run_date equals today, the trigger is not due."""
        today = date(2025, 6, 1)
        now = datetime(2025, 6, 1, 23, 59, tzinfo=UTC)
        assert is_daily_trigger_due(last_run_date=today, now=now) is False

    def test_returns_true_when_last_run_was_yesterday(self) -> None:
        yesterday = date(2025, 5, 31)
        now = datetime(2025, 6, 1, 0, 1, tzinfo=UTC)
        assert is_daily_trigger_due(last_run_date=yesterday, now=now) is True

    def test_returns_true_when_last_run_was_multiple_days_ago(self) -> None:
        last = date(2025, 1, 1)
        now = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        assert is_daily_trigger_due(last_run_date=last, now=now) is True

    def test_uses_date_part_of_now_not_time(self) -> None:
        """Early morning run on the same day as last_run is still not due."""
        today = date(2025, 6, 1)
        now = datetime(2025, 6, 1, 0, 0, 1, tzinfo=UTC)
        assert is_daily_trigger_due(last_run_date=today, now=now) is False


# ---------------------------------------------------------------------------
# fetch_merged_prs — mocked HTTP
# ---------------------------------------------------------------------------


def _make_pr(merged_at: str, number: int = 1) -> dict:
    """Build a minimal GitHub PR dict."""
    return {"number": number, "merged_at": merged_at}


def _mock_urlopen(payload: list[dict]) -> MagicMock:
    """Return a context-manager mock that yields encoded JSON."""
    body = json.dumps(payload).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestFetchMergedPrs:
    """Tests for fetch_merged_prs()."""

    def test_returns_prs_merged_after_since(self) -> None:
        """PRs whose merged_at is strictly after *since* are returned."""
        since = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        payload = [
            _make_pr("2025-06-01T13:00:00Z", number=42),
        ]
        with patch(
            "pipeline.trigger.github.urllib.request.urlopen", return_value=_mock_urlopen(payload)
        ):
            result = fetch_merged_prs(repo="owner/repo", gh_token="tok", since=since)

        assert len(result) == 1
        assert result[0]["number"] == 42

    def test_excludes_prs_merged_before_since(self) -> None:
        since = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        payload = [
            _make_pr("2025-06-01T11:59:00Z", number=10),
        ]
        with patch(
            "pipeline.trigger.github.urllib.request.urlopen", return_value=_mock_urlopen(payload)
        ):
            result = fetch_merged_prs(repo="owner/repo", gh_token="tok", since=since)

        assert result == []

    def test_excludes_prs_merged_at_exactly_since(self) -> None:
        """PRs merged at exactly *since* (not strictly after) are excluded."""
        since = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        payload = [_make_pr("2025-06-01T12:00:00Z", number=5)]
        with patch(
            "pipeline.trigger.github.urllib.request.urlopen", return_value=_mock_urlopen(payload)
        ):
            result = fetch_merged_prs(repo="owner/repo", gh_token="tok", since=since)

        assert result == []

    def test_excludes_unmerged_prs(self) -> None:
        """Closed but unmerged PRs (merged_at=None) are not returned."""
        since = datetime(2025, 1, 1, tzinfo=UTC)
        payload = [{"number": 7, "merged_at": None}]
        with patch(
            "pipeline.trigger.github.urllib.request.urlopen", return_value=_mock_urlopen(payload)
        ):
            result = fetch_merged_prs(repo="owner/repo", gh_token="tok", since=since)

        assert result == []

    def test_returns_empty_list_on_network_error(self) -> None:
        """URLError is swallowed and an empty list is returned."""
        since = datetime(2025, 1, 1, tzinfo=UTC)
        with patch(
            "pipeline.trigger.github.urllib.request.urlopen",
            side_effect=urllib.error.URLError("timeout"),
        ):
            result = fetch_merged_prs(repo="owner/repo", gh_token="tok", since=since)

        assert result == []

    def test_raises_value_error_for_repo_without_slash(self) -> None:
        with pytest.raises(ValueError, match="owner/repo"):
            fetch_merged_prs(
                repo="badformat", gh_token="tok", since=datetime(2025, 1, 1, tzinfo=UTC)
            )

    def test_filters_mixed_payload(self) -> None:
        """Only PRs strictly after *since* are included."""
        since = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        payload = [
            _make_pr("2025-06-01T11:00:00Z", number=1),  # before
            _make_pr("2025-06-01T13:00:00Z", number=2),  # after
            _make_pr("2025-06-01T14:00:00Z", number=3),  # after
        ]
        with patch(
            "pipeline.trigger.github.urllib.request.urlopen", return_value=_mock_urlopen(payload)
        ):
            result = fetch_merged_prs(repo="owner/repo", gh_token="tok", since=since)

        assert {pr["number"] for pr in result} == {2, 3}

    def test_treats_naive_since_as_utc(self) -> None:
        """Naive *since* datetimes are treated as UTC for comparison."""
        since_naive = datetime(2025, 6, 1, 12, 0)  # no tzinfo
        payload = [_make_pr("2025-06-01T13:00:00Z", number=99)]
        with patch(
            "pipeline.trigger.github.urllib.request.urlopen", return_value=_mock_urlopen(payload)
        ):
            result = fetch_merged_prs(repo="owner/repo", gh_token="tok", since=since_naive)

        assert len(result) == 1


# ---------------------------------------------------------------------------
# has_merged_prs_since — env token gating
# ---------------------------------------------------------------------------


class TestHasMergedPrsSince:
    """Tests for has_merged_prs_since()."""

    def test_returns_false_when_gh_token_absent(self) -> None:
        """No GH_TOKEN → no network call, returns False."""
        since = datetime(2025, 1, 1, tzinfo=UTC)
        with patch.dict("os.environ", {}, clear=True):
            # Ensure GH_TOKEN is absent.
            import os

            os.environ.pop("GH_TOKEN", None)
            result = has_merged_prs_since(repo="owner/repo", since=since)

        assert result is False

    def test_returns_true_when_merged_pr_exists(self) -> None:
        since = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        payload = [_make_pr("2025-06-01T13:00:00Z")]
        with (
            patch.dict("os.environ", {"GH_TOKEN": "test-token"}),
            patch(
                "pipeline.trigger.github.urllib.request.urlopen",
                return_value=_mock_urlopen(payload),
            ),
        ):
            result = has_merged_prs_since(repo="owner/repo", since=since)

        assert result is True

    def test_returns_false_when_no_merged_prs(self) -> None:
        since = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        with (
            patch.dict("os.environ", {"GH_TOKEN": "test-token"}),
            patch("pipeline.trigger.github.urllib.request.urlopen", return_value=_mock_urlopen([])),
        ):
            result = has_merged_prs_since(repo="owner/repo", since=since)

        assert result is False

    def test_returns_false_on_network_error(self) -> None:
        since = datetime(2025, 1, 1, tzinfo=UTC)
        with (
            patch.dict("os.environ", {"GH_TOKEN": "test-token"}),
            patch(
                "pipeline.trigger.github.urllib.request.urlopen",
                side_effect=urllib.error.URLError("connection refused"),
            ),
        ):
            result = has_merged_prs_since(repo="owner/repo", since=since)

        assert result is False


# ---------------------------------------------------------------------------
# TriggerEngine helpers
# ---------------------------------------------------------------------------


def _make_config(*repos: tuple[str, list[str], list[str]]) -> PipelineConfig:
    """Build a PipelineConfig from (repo_slug, triggers, agents) tuples."""
    return PipelineConfig(
        repos={
            slug: RepoConfig(triggers=triggers, analysis_agents=agents)
            for slug, triggers, agents in repos
        }
    )


def _fixed_clock(dt: datetime):
    """Return a callable that always returns *dt*."""
    return lambda: dt


# ---------------------------------------------------------------------------
# TriggerEngine.evaluate_repo — daily trigger
# ---------------------------------------------------------------------------


class TestTriggerEngineDaily:
    """evaluate_repo() with a daily trigger."""

    def test_daily_trigger_fires_when_never_run(self) -> None:
        """First evaluation always fires the daily trigger."""
        run_calls: list[tuple] = []
        config = _make_config(("owner/repo", [TRIGGER_DAILY], ["bot"]))
        now = datetime(2025, 6, 1, 9, 0, tzinfo=UTC)
        engine = TriggerEngine(
            config, run_pipeline=lambda **kw: run_calls.append(kw), clock=_fixed_clock(now)
        )

        fired = engine.evaluate_repo("owner/repo")

        assert fired is True
        assert len(run_calls) == 1
        assert run_calls[0]["repo"] == "owner/repo"
        assert run_calls[0]["agents"] == ["bot"]

    def test_daily_trigger_does_not_fire_twice_same_day(self) -> None:
        """Second evaluation on the same day is a no-op."""
        run_calls: list[tuple] = []
        config = _make_config(("owner/repo", [TRIGGER_DAILY], ["bot"]))
        now = datetime(2025, 6, 1, 9, 0, tzinfo=UTC)
        engine = TriggerEngine(
            config, run_pipeline=lambda **kw: run_calls.append(kw), clock=_fixed_clock(now)
        )

        engine.evaluate_repo("owner/repo")
        fired_second = engine.evaluate_repo("owner/repo")

        assert fired_second is False
        assert len(run_calls) == 1

    def test_daily_trigger_fires_again_next_day(self) -> None:
        """Evaluation on the next calendar day fires again."""
        run_calls: list[tuple] = []
        config = _make_config(("owner/repo", [TRIGGER_DAILY], ["bot"]))

        day1 = datetime(2025, 6, 1, 9, 0, tzinfo=UTC)
        day2 = datetime(2025, 6, 2, 9, 0, tzinfo=UTC)

        engine = TriggerEngine(
            config, run_pipeline=lambda **kw: run_calls.append(kw), clock=_fixed_clock(day1)
        )
        engine.evaluate_repo("owner/repo")

        engine._clock = _fixed_clock(day2)
        engine.evaluate_repo("owner/repo")

        assert len(run_calls) == 2

    def test_daily_trigger_last_daily_run_updated(self) -> None:
        """Internal last_daily_run date is set to today after the trigger fires."""
        config = _make_config(("owner/repo", [TRIGGER_DAILY], []))
        now = datetime(2025, 6, 1, tzinfo=UTC)
        engine = TriggerEngine(config, run_pipeline=lambda **_kw: None, clock=_fixed_clock(now))

        engine.evaluate_repo("owner/repo")

        assert engine._last_daily_run.get("owner/repo") == date(2025, 6, 1)


# ---------------------------------------------------------------------------
# TriggerEngine.evaluate_repo — pr_merge trigger
# ---------------------------------------------------------------------------


class TestTriggerEnginePrMerge:
    """evaluate_repo() with a pr_merge trigger."""

    def test_pr_merge_fires_when_merged_pr_detected(self) -> None:
        run_calls: list[dict] = []
        config = _make_config(("owner/repo", [TRIGGER_PR_MERGE], ["auditor"]))
        now = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        engine = TriggerEngine(
            config, run_pipeline=lambda **kw: run_calls.append(kw), clock=_fixed_clock(now)
        )

        with patch("pipeline.trigger.engine.has_merged_prs_since", return_value=True):
            fired = engine.evaluate_repo("owner/repo")

        assert fired is True
        assert run_calls[0]["repo"] == "owner/repo"

    def test_pr_merge_does_not_fire_when_no_prs(self) -> None:
        run_calls: list[dict] = []
        config = _make_config(("owner/repo", [TRIGGER_PR_MERGE], []))
        now = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        engine = TriggerEngine(
            config, run_pipeline=lambda **kw: run_calls.append(kw), clock=_fixed_clock(now)
        )

        with patch("pipeline.trigger.engine.has_merged_prs_since", return_value=False):
            fired = engine.evaluate_repo("owner/repo")

        assert fired is False
        assert run_calls == []

    def test_pr_check_cursor_advances_on_each_call(self) -> None:
        """_last_pr_check is updated to *now* regardless of whether a PR was found."""
        config = _make_config(("owner/repo", [TRIGGER_PR_MERGE], []))
        t1 = datetime(2025, 6, 1, 10, 0, tzinfo=UTC)
        engine = TriggerEngine(config, run_pipeline=lambda **_kw: None, clock=_fixed_clock(t1))

        with patch("pipeline.trigger.engine.has_merged_prs_since", return_value=False):
            engine.evaluate_repo("owner/repo")

        assert engine._last_pr_check.get("owner/repo") == t1

    def test_pr_merge_first_evaluation_uses_now_as_since(self) -> None:
        """On the first poll, *since* defaults to *now* to avoid historical PRs."""
        seen_since: list[datetime] = []
        config = _make_config(("owner/repo", [TRIGGER_PR_MERGE], []))
        now = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        engine = TriggerEngine(config, run_pipeline=lambda **_kw: None, clock=_fixed_clock(now))

        def capture_since(repo: str, since: datetime) -> bool:
            seen_since.append(since)
            return False

        with patch("pipeline.trigger.engine.has_merged_prs_since", side_effect=capture_since):
            engine.evaluate_repo("owner/repo")

        assert seen_since[0] == now


# ---------------------------------------------------------------------------
# TriggerEngine.evaluate_repo — unknown repo and no trigger
# ---------------------------------------------------------------------------


class TestTriggerEngineEvaluateEdgeCases:
    """Edge cases for evaluate_repo()."""

    def test_returns_false_for_unknown_repo(self) -> None:
        config = _make_config()
        engine = TriggerEngine(config, run_pipeline=lambda **_kw: None)
        assert engine.evaluate_repo("unknown/repo") is False

    def test_manual_trigger_not_fired_by_evaluate_repo(self) -> None:
        """evaluate_repo() never fires the manual trigger."""
        run_calls: list[dict] = []
        config = _make_config(("owner/repo", [TRIGGER_MANUAL], []))
        engine = TriggerEngine(config, run_pipeline=lambda **kw: run_calls.append(kw))

        engine.evaluate_repo("owner/repo")

        assert run_calls == []

    def test_only_first_matching_trigger_fires(self) -> None:
        """When both daily and pr_merge are configured, only the first fires."""
        run_calls: list[dict] = []
        config = _make_config(("owner/repo", [TRIGGER_DAILY, TRIGGER_PR_MERGE], ["bot"]))
        now = datetime(2025, 6, 1, 9, 0, tzinfo=UTC)
        engine = TriggerEngine(
            config, run_pipeline=lambda **kw: run_calls.append(kw), clock=_fixed_clock(now)
        )

        with patch("pipeline.trigger.engine.has_merged_prs_since", return_value=True):
            engine.evaluate_repo("owner/repo")

        # Fired once (daily fired first, stopped evaluation).
        assert len(run_calls) == 1


# ---------------------------------------------------------------------------
# TriggerEngine.fire_manual
# ---------------------------------------------------------------------------


class TestTriggerEngineFireManual:
    """fire_manual() immediately invokes the pipeline."""

    def test_fires_pipeline_for_repo_with_manual_trigger(self) -> None:
        run_calls: list[dict] = []
        config = _make_config(("owner/repo", [TRIGGER_MANUAL], ["analyzer"]))
        engine = TriggerEngine(config, run_pipeline=lambda **kw: run_calls.append(kw))

        engine.fire_manual("owner/repo")

        assert len(run_calls) == 1
        assert run_calls[0]["repo"] == "owner/repo"
        assert run_calls[0]["agents"] == ["analyzer"]

    def test_raises_for_unknown_repo(self) -> None:
        config = _make_config()
        engine = TriggerEngine(config, run_pipeline=lambda **_kw: None)

        with pytest.raises(ValueError, match="Unknown repo"):
            engine.fire_manual("missing/repo")

    def test_raises_when_manual_trigger_not_configured(self) -> None:
        config = _make_config(("owner/repo", [TRIGGER_DAILY], []))
        engine = TriggerEngine(config, run_pipeline=lambda **_kw: None)

        with pytest.raises(ValueError, match="manual"):
            engine.fire_manual("owner/repo")


# ---------------------------------------------------------------------------
# TriggerEngine.run_once
# ---------------------------------------------------------------------------


class TestTriggerEngineRunOnce:
    """run_once() evaluates all repos."""

    def test_evaluates_all_configured_repos(self) -> None:
        evaluated: list[str] = []
        config = _make_config(
            ("alpha/repo", [TRIGGER_DAILY], []),
            ("beta/repo", [TRIGGER_DAILY], []),
        )
        now = datetime(2025, 6, 1, tzinfo=UTC)
        engine = TriggerEngine(
            config,
            run_pipeline=lambda **kw: evaluated.append(kw["repo"]),
            clock=_fixed_clock(now),
        )

        engine.run_once()

        assert set(evaluated) == {"alpha/repo", "beta/repo"}

    def test_run_once_with_empty_config_does_nothing(self) -> None:
        """No repos configured → run_once is a no-op."""
        config = _make_config()
        engine = TriggerEngine(config, run_pipeline=lambda **_kw: None)
        engine.run_once()  # should not raise
