"""Tests for pipeline.telemetry — TelemetryStore and CycleMetrics computation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from beads.types import CycleBead, ProposalBead, SuppressionBead

from pipeline.telemetry.metrics import (
    CONSECUTIVE_CYCLE_ALERT_COUNT,
    REVIEW_TIME_THRESHOLD_SECONDS,
    CycleMetrics,
    check_review_time_alert,
    compute_cycle_metrics,
)
from pipeline.telemetry.store import TelemetryStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO = "owner/repo"
CYCLE_ID = "cycle-telem-test"


def _cycle(
    finding_count: int = 0,
    proposal_count: int = 0,
    total_cost_usd: float = 0.0,
) -> CycleBead:
    return CycleBead(
        cycle_id=CYCLE_ID,
        repo=REPO,
        finding_count=finding_count,
        proposal_count=proposal_count,
        total_cost_usd=total_cost_usd,
    )


def _proposal(
    proposal_id: str,
    status: str = "pending",
    review_seconds: float | None = None,
) -> ProposalBead:
    return ProposalBead(
        proposal_id=proposal_id,
        cycle_id=CYCLE_ID,
        repo=REPO,
        spec_hash="abc123",
        spec_path="path/to/spec",
        status=status,
        review_seconds=review_seconds,
    )


def _suppression(suppression_id: str) -> SuppressionBead:
    return SuppressionBead(
        suppression_id=suppression_id,
        finding_class="repo-audit.integration-gap.executor",
        decision="rejected",
        reason="not relevant",
        created_by="operator",
    )


def _metrics_with_review(seconds: float | None) -> CycleMetrics:
    return CycleMetrics(
        approval_rate=0.0,
        rejection_rate=0.0,
        deferral_rate=0.0,
        median_review_seconds=seconds,
        suppression_count=0,
        total_analysis_cost_usd=0.0,
        finding_count=0,
        proposal_count=0,
    )


# ---------------------------------------------------------------------------
# TelemetryStore.append and TelemetryStore.path
# ---------------------------------------------------------------------------


class TestTelemetryStoreAppend:
    """TelemetryStore.append writes records as JSONL."""

    def test_path_includes_owner_and_repo(self, tmp_path: Path) -> None:
        store = TelemetryStore("myowner", "myrepo", base_dir=tmp_path)
        assert store.path == tmp_path / "telemetry" / "myowner-myrepo.jsonl"

    def test_append_creates_parent_directory(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append({"cycle_id": CYCLE_ID})
        assert store.path.exists()

    def test_append_writes_valid_json_line(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append({"key": "value", "num": 42})
        line = store.path.read_text().strip()
        parsed = json.loads(line)
        assert parsed == {"key": "value", "num": 42}

    def test_append_adds_newline_after_record(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append({"a": 1})
        raw = store.path.read_text()
        assert raw.endswith("\n")

    def test_append_multiple_records_each_on_own_line(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append({"n": 1})
        store.append({"n": 2})
        store.append({"n": 3})
        lines = [ln for ln in store.path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 3
        assert [json.loads(ln)["n"] for ln in lines] == [1, 2, 3]

    def test_append_preserves_all_field_types(self, tmp_path: Path) -> None:
        record = {
            "string": "hello",
            "integer": 7,
            "float_val": 3.14,
            "boolean": True,
            "null_val": None,
            "list_val": [1, 2, 3],
        }
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append(record)
        parsed = json.loads(store.path.read_text().strip())
        assert parsed == record


# ---------------------------------------------------------------------------
# TelemetryStore.read_all
# ---------------------------------------------------------------------------


class TestTelemetryStoreReadAll:
    """TelemetryStore.read_all parses JSONL records in order."""

    def test_returns_empty_list_when_file_missing(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        assert store.read_all() == []

    def test_returns_records_in_insertion_order(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        for i in range(5):
            store.append({"index": i})
        records = store.read_all()
        assert [r["index"] for r in records] == list(range(5))

    def test_round_trips_appended_records(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        original = [{"cycle_id": f"c{i}", "cost": i * 0.10} for i in range(3)]
        for r in original:
            store.append(r)
        assert store.read_all() == original

    def test_skips_blank_lines(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text('{"a": 1}\n\n{"b": 2}\n\n')
        records = store.read_all()
        assert len(records) == 2
        assert records[0] == {"a": 1}
        assert records[1] == {"b": 2}

    def test_single_record_round_trips(self, tmp_path: Path) -> None:
        store = TelemetryStore("owner", "repo", base_dir=tmp_path)
        store.append({"cycle_id": "abc", "proposals": 3, "cost_usd": 1.23})
        records = store.read_all()
        assert len(records) == 1
        assert records[0]["cycle_id"] == "abc"
        assert records[0]["proposals"] == 3


# ---------------------------------------------------------------------------
# compute_cycle_metrics — rates
# ---------------------------------------------------------------------------


class TestComputeCycleMetricsRates:
    """compute_cycle_metrics computes approval/rejection/deferral rates correctly."""

    def test_all_rates_zero_with_no_proposals(self) -> None:
        metrics = compute_cycle_metrics(_cycle(), [], [])
        assert metrics.approval_rate == 0.0
        assert metrics.rejection_rate == 0.0
        assert metrics.deferral_rate == 0.0

    def test_all_rates_zero_with_only_pending_proposals(self) -> None:
        proposals = [_proposal("p1", "pending"), _proposal("p2", "pending")]
        metrics = compute_cycle_metrics(_cycle(), proposals, [])
        assert metrics.approval_rate == 0.0
        assert metrics.rejection_rate == 0.0
        assert metrics.deferral_rate == 0.0

    def test_all_approved(self) -> None:
        proposals = [
            _proposal("p1", "approved"),
            _proposal("p2", "approved"),
        ]
        metrics = compute_cycle_metrics(_cycle(), proposals, [])
        assert metrics.approval_rate == pytest.approx(1.0)
        assert metrics.rejection_rate == pytest.approx(0.0)
        assert metrics.deferral_rate == pytest.approx(0.0)

    def test_all_rejected(self) -> None:
        proposals = [_proposal("p1", "rejected"), _proposal("p2", "rejected")]
        metrics = compute_cycle_metrics(_cycle(), proposals, [])
        assert metrics.approval_rate == pytest.approx(0.0)
        assert metrics.rejection_rate == pytest.approx(1.0)
        assert metrics.deferral_rate == pytest.approx(0.0)

    def test_all_deferred(self) -> None:
        proposals = [_proposal("p1", "deferred")]
        metrics = compute_cycle_metrics(_cycle(), proposals, [])
        assert metrics.deferral_rate == pytest.approx(1.0)
        assert metrics.approval_rate == pytest.approx(0.0)
        assert metrics.rejection_rate == pytest.approx(0.0)

    def test_mixed_decisions(self) -> None:
        proposals = [
            _proposal("p1", "approved"),
            _proposal("p2", "approved"),
            _proposal("p3", "rejected"),
            _proposal("p4", "deferred"),
        ]
        metrics = compute_cycle_metrics(_cycle(), proposals, [])
        assert metrics.approval_rate == pytest.approx(2 / 4)
        assert metrics.rejection_rate == pytest.approx(1 / 4)
        assert metrics.deferral_rate == pytest.approx(1 / 4)

    def test_pending_excluded_from_rate_denominator(self) -> None:
        """Pending proposals do not count toward the decided denominator."""
        proposals = [
            _proposal("p1", "approved"),
            _proposal("p2", "pending"),
        ]
        metrics = compute_cycle_metrics(_cycle(), proposals, [])
        # 1 decided (approved), denominator = 1
        assert metrics.approval_rate == pytest.approx(1.0)

    def test_rates_sum_to_one_for_fully_decided_cycle(self) -> None:
        proposals = [
            _proposal("p1", "approved"),
            _proposal("p2", "rejected"),
            _proposal("p3", "deferred"),
        ]
        metrics = compute_cycle_metrics(_cycle(), proposals, [])
        total = metrics.approval_rate + metrics.rejection_rate + metrics.deferral_rate
        assert total == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# compute_cycle_metrics — review times
# ---------------------------------------------------------------------------


class TestComputeCycleMetricsReviewTime:
    """compute_cycle_metrics computes median_review_seconds correctly."""

    def test_none_when_no_review_times(self) -> None:
        proposals = [_proposal("p1", "approved", review_seconds=None)]
        metrics = compute_cycle_metrics(_cycle(), proposals, [])
        assert metrics.median_review_seconds is None

    def test_none_when_proposals_empty(self) -> None:
        metrics = compute_cycle_metrics(_cycle(), [], [])
        assert metrics.median_review_seconds is None

    def test_single_review_time_is_median(self) -> None:
        proposals = [_proposal("p1", "approved", review_seconds=120.0)]
        metrics = compute_cycle_metrics(_cycle(), proposals, [])
        assert metrics.median_review_seconds == pytest.approx(120.0)

    def test_median_of_odd_number_of_times(self) -> None:
        proposals = [
            _proposal("p1", review_seconds=60.0),
            _proposal("p2", review_seconds=120.0),
            _proposal("p3", review_seconds=300.0),
        ]
        metrics = compute_cycle_metrics(_cycle(), proposals, [])
        assert metrics.median_review_seconds == pytest.approx(120.0)

    def test_median_of_even_number_of_times(self) -> None:
        proposals = [
            _proposal("p1", review_seconds=100.0),
            _proposal("p2", review_seconds=200.0),
        ]
        metrics = compute_cycle_metrics(_cycle(), proposals, [])
        assert metrics.median_review_seconds == pytest.approx(150.0)

    def test_none_review_times_excluded_from_median(self) -> None:
        proposals = [
            _proposal("p1", review_seconds=100.0),
            _proposal("p2", review_seconds=None),
            _proposal("p3", review_seconds=200.0),
        ]
        metrics = compute_cycle_metrics(_cycle(), proposals, [])
        assert metrics.median_review_seconds == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# compute_cycle_metrics — other fields
# ---------------------------------------------------------------------------


class TestComputeCycleMetricsFields:
    """compute_cycle_metrics forwards counts and cost from bead/suppression list."""

    def test_suppression_count_matches_suppression_list_length(self) -> None:
        suppressions = [_suppression("s1"), _suppression("s2"), _suppression("s3")]
        metrics = compute_cycle_metrics(_cycle(), [], suppressions)
        assert metrics.suppression_count == 3

    def test_suppression_count_zero_when_no_suppressions(self) -> None:
        metrics = compute_cycle_metrics(_cycle(), [], [])
        assert metrics.suppression_count == 0

    def test_total_analysis_cost_from_cycle_bead(self) -> None:
        metrics = compute_cycle_metrics(_cycle(total_cost_usd=4.56), [], [])
        assert metrics.total_analysis_cost_usd == pytest.approx(4.56)

    def test_finding_count_from_cycle_bead(self) -> None:
        metrics = compute_cycle_metrics(_cycle(finding_count=7), [], [])
        assert metrics.finding_count == 7

    def test_proposal_count_from_cycle_bead(self) -> None:
        metrics = compute_cycle_metrics(_cycle(proposal_count=3), [], [])
        assert metrics.proposal_count == 3

    def test_all_fields_populated_in_single_call(self) -> None:
        cycle = _cycle(finding_count=4, proposal_count=2, total_cost_usd=1.0)
        proposals = [
            _proposal("p1", "approved", review_seconds=60.0),
            _proposal("p2", "rejected", review_seconds=120.0),
        ]
        suppressions = [_suppression("s1")]
        metrics = compute_cycle_metrics(cycle, proposals, suppressions)

        assert metrics.finding_count == 4
        assert metrics.proposal_count == 2
        assert metrics.total_analysis_cost_usd == pytest.approx(1.0)
        assert metrics.suppression_count == 1
        assert metrics.approval_rate == pytest.approx(0.5)
        assert metrics.rejection_rate == pytest.approx(0.5)
        assert metrics.median_review_seconds == pytest.approx(90.0)


# ---------------------------------------------------------------------------
# check_review_time_alert
# ---------------------------------------------------------------------------


class TestCheckReviewTimeAlert:
    """check_review_time_alert fires after CONSECUTIVE_CYCLE_ALERT_COUNT slow cycles."""

    def test_false_when_no_metrics(self) -> None:
        assert check_review_time_alert([]) is False

    def test_false_with_fewer_than_required_cycles(self) -> None:
        fast = _metrics_with_review(REVIEW_TIME_THRESHOLD_SECONDS + 1)
        metrics = [fast] * (CONSECUTIVE_CYCLE_ALERT_COUNT - 1)
        assert check_review_time_alert(metrics) is False

    def test_true_when_last_n_all_exceed_threshold(self) -> None:
        slow = _metrics_with_review(REVIEW_TIME_THRESHOLD_SECONDS + 1)
        metrics = [slow] * CONSECUTIVE_CYCLE_ALERT_COUNT
        assert check_review_time_alert(metrics) is True

    def test_false_when_one_of_last_n_is_below_threshold(self) -> None:
        slow = _metrics_with_review(REVIEW_TIME_THRESHOLD_SECONDS + 1)
        fast = _metrics_with_review(REVIEW_TIME_THRESHOLD_SECONDS - 1)
        metrics = [slow, slow, fast]
        assert check_review_time_alert(metrics) is False

    def test_false_when_one_of_last_n_has_no_review_time(self) -> None:
        slow = _metrics_with_review(REVIEW_TIME_THRESHOLD_SECONDS + 1)
        no_data = _metrics_with_review(None)
        metrics = [slow, slow, no_data]
        assert check_review_time_alert(metrics) is False

    def test_only_last_n_cycles_are_checked(self) -> None:
        """Early fast cycles don't prevent the alert if the last N are all slow."""
        fast = _metrics_with_review(1.0)
        slow = _metrics_with_review(REVIEW_TIME_THRESHOLD_SECONDS + 1)
        # Prepend many fast cycles; only the trailing N matter.
        metrics = [fast] * 20 + [slow] * CONSECUTIVE_CYCLE_ALERT_COUNT
        assert check_review_time_alert(metrics) is True

    def test_false_when_exactly_at_threshold_not_above(self) -> None:
        """Exactly at threshold is NOT slow enough to trigger."""
        at_threshold = _metrics_with_review(REVIEW_TIME_THRESHOLD_SECONDS)
        metrics = [at_threshold] * CONSECUTIVE_CYCLE_ALERT_COUNT
        assert check_review_time_alert(metrics) is False

    def test_custom_threshold_respected(self) -> None:
        custom_threshold = 600.0
        slow = _metrics_with_review(700.0)
        metrics = [slow] * CONSECUTIVE_CYCLE_ALERT_COUNT
        assert check_review_time_alert(metrics, threshold_seconds=custom_threshold) is True

    def test_custom_consecutive_cycles_respected(self) -> None:
        slow = _metrics_with_review(REVIEW_TIME_THRESHOLD_SECONDS + 1)
        # Only 2 slow cycles; alert fires only if consecutive_cycles=2.
        assert check_review_time_alert([slow, slow], consecutive_cycles=2) is True
        assert check_review_time_alert([slow, slow], consecutive_cycles=3) is False

    def test_constant_values_are_named(self) -> None:
        """Module constants are accessible for overriding in callers."""
        assert REVIEW_TIME_THRESHOLD_SECONDS == 300.0
        assert CONSECUTIVE_CYCLE_ALERT_COUNT == 3
