"""Tests for SuppressionBead.is_active(), _derive_finding_class, and write_suppression."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from beads.types import SuppressionBead

from pipeline.suppression.bead_writer import _derive_finding_class, write_suppression


class TestSuppressionBeadIsActive:
    """Tests for SuppressionBead.is_active()."""

    def test_permanent_suppression_is_always_active(self) -> None:
        """A suppression with no expiry is permanently active."""
        bead = SuppressionBead(
            suppression_id="s-1",
            finding_class="repo-audit.integration-gap",
            decision="rejected",
            reason="known issue",
            created_by="reviewer",
            expires_at=None,
        )
        assert bead.is_active() is True

    def test_future_expiry_is_active(self) -> None:
        """A suppression expiring in the future is active."""
        bead = SuppressionBead(
            suppression_id="s-2",
            finding_class="repo-audit.integration-gap",
            decision="deferred",
            reason="revisit later",
            created_by="reviewer",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert bead.is_active() is True

    def test_past_expiry_is_inactive(self) -> None:
        """A suppression whose expires_at is in the past is inactive."""
        bead = SuppressionBead(
            suppression_id="s-3",
            finding_class="repo-audit.integration-gap",
            decision="rejected",
            reason="expired",
            created_by="reviewer",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        assert bead.is_active() is False

    def test_expiry_boundary_just_past_is_inactive(self) -> None:
        """A suppression that expired even one microsecond ago is inactive."""
        bead = SuppressionBead(
            suppression_id="s-4",
            finding_class="repo-audit.integration-gap",
            decision="rejected",
            reason="just expired",
            created_by="reviewer",
            expires_at=datetime.now(UTC) - timedelta(microseconds=1),
        )
        assert bead.is_active() is False

    def test_expiry_boundary_in_future_is_active(self) -> None:
        """A suppression expiring one day from now is active."""
        bead = SuppressionBead(
            suppression_id="s-5",
            finding_class="repo-audit.integration-gap",
            decision="deferred",
            reason="far future",
            created_by="reviewer",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        assert bead.is_active() is True


class TestDeriveFindingClass:
    """Tests for _derive_finding_class()."""

    def test_single_id_returns_itself(self) -> None:
        """A single finding ID is its own class."""
        assert _derive_finding_class(["repo-audit.integration-gap.executor"]) == (
            "repo-audit.integration-gap.executor"
        )

    def test_two_ids_with_common_prefix(self) -> None:
        """Common prefix of two IDs is returned."""
        result = _derive_finding_class(["abc.def", "abc.ghi"])
        assert result == "abc."

    def test_three_ids_with_common_prefix(self) -> None:
        """Longest common prefix of three IDs is returned."""
        result = _derive_finding_class(["repo.gap.auth", "repo.gap.exec", "repo.gap.db"])
        assert result == "repo.gap."

    def test_no_common_prefix_returns_empty_string(self) -> None:
        """IDs with no shared prefix produce an empty string."""
        assert _derive_finding_class(["abc", "def"]) == ""

    def test_one_id_is_prefix_of_another(self) -> None:
        """When one ID is a strict prefix of another, it returns the shorter ID."""
        assert _derive_finding_class(["ab", "abc"]) == "ab"

    def test_identical_ids_return_that_id(self) -> None:
        """Identical IDs produce the full shared string."""
        assert _derive_finding_class(["same.id", "same.id", "same.id"]) == "same.id"

    def test_empty_list_raises_value_error(self) -> None:
        """An empty finding_ids list raises ValueError."""
        with pytest.raises(ValueError, match="finding_ids must not be empty"):
            _derive_finding_class([])


class TestWriteSuppression:
    """Tests for write_suppression()."""

    def test_returns_suppression_bead_with_correct_finding_class(self) -> None:
        """write_suppression derives finding_class from the finding IDs."""
        store = MagicMock()
        bead = write_suppression(
            store=store,
            finding_ids=["repo-audit.gap.auth", "repo-audit.gap.exec"],
            decision="rejected",
            reason="not a real gap",
            created_by="alice",
        )
        assert bead.finding_class == "repo-audit.gap."

    def test_calls_store_write_suppression(self) -> None:
        """write_suppression persists the bead via store.write_suppression."""
        store = MagicMock()
        bead = write_suppression(
            store=store,
            finding_ids=["a.b.c"],
            decision="deferred",
            reason="defer for now",
            created_by="bob",
        )
        store.write_suppression.assert_called_once_with(bead)

    def test_returned_bead_fields_match_inputs(self) -> None:
        """write_suppression populates all bead fields from the arguments."""
        store = MagicMock()
        expires = datetime(2030, 1, 1, tzinfo=UTC)
        bead = write_suppression(
            store=store,
            finding_ids=["x.y"],
            decision="rejected",
            reason="intentional",
            created_by="carol",
            expires_at=expires,
        )
        assert bead.decision == "rejected"
        assert bead.reason == "intentional"
        assert bead.created_by == "carol"
        assert bead.expires_at == expires

    def test_expires_at_none_by_default(self) -> None:
        """write_suppression defaults to a permanent suppression."""
        store = MagicMock()
        bead = write_suppression(
            store=store,
            finding_ids=["m.n"],
            decision="rejected",
            reason="permanent",
            created_by="dave",
        )
        assert bead.expires_at is None

    def test_suppression_id_is_set(self) -> None:
        """write_suppression assigns a non-empty suppression_id."""
        store = MagicMock()
        bead = write_suppression(
            store=store,
            finding_ids=["p.q"],
            decision="deferred",
            reason="test",
            created_by="eve",
        )
        assert bead.suppression_id != ""

    def test_empty_finding_ids_raises_value_error(self) -> None:
        """write_suppression propagates ValueError for empty finding_ids."""
        store = MagicMock()
        with pytest.raises(ValueError, match="finding_ids must not be empty"):
            write_suppression(
                store=store,
                finding_ids=[],
                decision="rejected",
                reason="oops",
                created_by="frank",
            )

    def test_unique_suppression_ids_across_calls(self) -> None:
        """Each write_suppression call produces a distinct suppression_id."""
        store = MagicMock()
        bead_a = write_suppression(
            store=store,
            finding_ids=["a"],
            decision="rejected",
            reason="r",
            created_by="g",
        )
        bead_b = write_suppression(
            store=store,
            finding_ids=["b"],
            decision="rejected",
            reason="r",
            created_by="g",
        )
        assert bead_a.suppression_id != bead_b.suppression_id

    def test_created_at_is_set_to_now(self) -> None:
        """write_suppression stamps created_at with the current UTC time."""
        store = MagicMock()
        before = datetime.now(UTC)
        bead = write_suppression(
            store=store,
            finding_ids=["z"],
            decision="rejected",
            reason="timestamp test",
            created_by="henry",
        )
        after = datetime.now(UTC)
        assert before <= bead.created_at <= after
