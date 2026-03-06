"""Tests for SuppressionsFilter.filter()."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from beads.types import FindingBead, SuppressionBead

from pipeline.suppression.filter import SuppressionsFilter

_TIMESTAMP = datetime(2024, 1, 1, tzinfo=UTC)


def _make_finding(id: str, repo: str = "owner/repo") -> FindingBead:
    return FindingBead(
        id=id,
        agent="repo-audit",
        timestamp=_TIMESTAMP,
        staleness_class="structural",
        confidence=0.9,
        reasoning="test finding",
        severity="medium",
        repo=repo,
        cycle_id="cycle-1",
    )


def _make_suppression(finding_class: str) -> SuppressionBead:
    return SuppressionBead(
        suppression_id="sup-1",
        finding_class=finding_class,
        decision="rejected",
        reason="test",
        created_by="tester",
        expires_at=None,
    )


class TestSuppressionsFilterFilter:
    """Tests for SuppressionsFilter.filter()."""

    def test_no_active_suppressions_returns_all_findings(self) -> None:
        """When no suppressions are active, all findings pass through."""
        store = MagicMock()
        store.list_active_suppressions.return_value = []
        f = SuppressionsFilter(store)

        findings = [_make_finding("repo-audit.gap.auth"), _make_finding("repo-audit.gap.exec")]
        result = f.filter(findings)

        assert result == findings

    def test_matching_prefix_suppresses_finding(self) -> None:
        """A finding whose ID starts with the suppression's finding_class is removed."""
        store = MagicMock()
        store.list_active_suppressions.return_value = [_make_suppression("repo-audit.gap.")]
        f = SuppressionsFilter(store)

        findings = [_make_finding("repo-audit.gap.auth")]
        result = f.filter(findings)

        assert result == []

    def test_non_matching_prefix_keeps_finding(self) -> None:
        """A finding whose ID does not start with any suppression prefix passes through."""
        store = MagicMock()
        store.list_active_suppressions.return_value = [_make_suppression("repo-audit.gap.")]
        f = SuppressionsFilter(store)

        findings = [_make_finding("repo-audit.integration.auth")]
        result = f.filter(findings)

        assert result == findings

    def test_partial_match_against_multiple_suppressions(self) -> None:
        """Only findings that match at least one suppression prefix are removed."""
        store = MagicMock()
        store.list_active_suppressions.return_value = [
            _make_suppression("repo-audit.gap."),
            _make_suppression("repo-audit.stale."),
        ]
        f = SuppressionsFilter(store)

        keep = _make_finding("repo-audit.integration.auth")
        suppress1 = _make_finding("repo-audit.gap.db")
        suppress2 = _make_finding("repo-audit.stale.executor")
        result = f.filter([keep, suppress1, suppress2])

        assert result == [keep]

    def test_exact_id_equals_finding_class_is_suppressed(self) -> None:
        """A finding whose ID exactly equals the finding_class is suppressed (startswith is inclusive)."""
        store = MagicMock()
        store.list_active_suppressions.return_value = [_make_suppression("exact.match")]
        f = SuppressionsFilter(store)

        result = f.filter([_make_finding("exact.match")])

        assert result == []

    def test_empty_findings_returns_empty(self) -> None:
        """Filtering an empty list returns an empty list."""
        store = MagicMock()
        store.list_active_suppressions.return_value = [_make_suppression("repo-audit.")]
        f = SuppressionsFilter(store)

        assert f.filter([]) == []

    def test_expired_suppression_not_filtered_because_store_excludes_it(self) -> None:
        """Expired suppressions are excluded by the store; findings are not suppressed."""
        store = MagicMock()
        # The store returns nothing — it has already excluded the expired suppression.
        store.list_active_suppressions.return_value = []
        f = SuppressionsFilter(store)

        finding = _make_finding("repo-audit.gap.auth")
        result = f.filter([finding])

        assert result == [finding]

    def test_repo_kwarg_is_forwarded_to_store(self) -> None:
        """The repo argument is passed through to store.list_active_suppressions."""
        store = MagicMock()
        store.list_active_suppressions.return_value = []
        f = SuppressionsFilter(store)

        f.filter([_make_finding("x")], repo="owner/repo")

        store.list_active_suppressions.assert_called_once_with(repo="owner/repo")

    def test_repo_kwarg_none_is_forwarded_to_store(self) -> None:
        """When repo is not provided, None is forwarded to the store."""
        store = MagicMock()
        store.list_active_suppressions.return_value = []
        f = SuppressionsFilter(store)

        f.filter([_make_finding("x")])

        store.list_active_suppressions.assert_called_once_with(repo=None)

    def test_result_is_a_new_list(self) -> None:
        """filter() always returns a new list, not the input list."""
        store = MagicMock()
        store.list_active_suppressions.return_value = []
        f = SuppressionsFilter(store)

        findings = [_make_finding("a.b.c")]
        result = f.filter(findings)

        assert result is not findings

    def test_empty_string_finding_class_suppresses_everything(self) -> None:
        """An empty finding_class prefix matches all finding IDs (startswith(''))."""
        store = MagicMock()
        store.list_active_suppressions.return_value = [_make_suppression("")]
        f = SuppressionsFilter(store)

        findings = [_make_finding("anything"), _make_finding("other")]
        result = f.filter(findings)

        assert result == []
