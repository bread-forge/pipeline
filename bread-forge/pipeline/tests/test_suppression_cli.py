"""Tests for pipeline suppressions CLI commands: list and expire."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from beads.types import SuppressionBead
from typer.testing import CliRunner

from pipeline.cli.main import app
from pipeline.store.beadstore import get_store

runner = CliRunner()

_REPO = "owner/repo"


def _make_store(tmp_path: Path) -> object:
    return get_store(_REPO, beads_dir=tmp_path)


def _make_suppression(
    suppression_id: str = "sup-abc-123",
    finding_class: str = "repo-audit.gap.",
    decision: str = "rejected",
    reason: str = "not a real issue",
    created_by: str = "alice",
    expires_at: datetime | None = None,
) -> SuppressionBead:
    return SuppressionBead(
        suppression_id=suppression_id,
        finding_class=finding_class,
        decision=decision,
        reason=reason,
        created_by=created_by,
        expires_at=expires_at,
    )


class TestListSuppressionsCommand:
    """Tests for `pipeline suppressions list`."""

    def test_no_suppressions_prints_empty_message(self, tmp_path: Path) -> None:
        """When no suppressions are active, the command says so."""
        store = _make_store(tmp_path)
        with patch("pipeline.cli.commands.suppressions.get_store", return_value=store):
            result = runner.invoke(app, ["suppressions", "list", "--repo", _REPO])
        assert result.exit_code == 0
        assert "No active suppressions" in result.output

    def test_active_suppression_appears_in_output(self, tmp_path: Path) -> None:
        """An active suppression is shown in the tabular output."""
        store = _make_store(tmp_path)
        sup = _make_suppression(suppression_id="sup-abc-123", finding_class="repo-audit.gap.")
        store.write_suppression(sup)  # type: ignore[attr-defined]

        with patch("pipeline.cli.commands.suppressions.get_store", return_value=store):
            result = runner.invoke(app, ["suppressions", "list", "--repo", _REPO])

        assert result.exit_code == 0
        assert "sup-abc-123" in result.output
        assert "repo-audit.gap." in result.output
        assert "rejected" in result.output
        assert "not a real issue" in result.output

    def test_permanent_suppression_shows_never_expiry(self, tmp_path: Path) -> None:
        """A suppression with no expiry shows 'never' in the EXPIRES_AT column."""
        store = _make_store(tmp_path)
        sup = _make_suppression(expires_at=None)
        store.write_suppression(sup)  # type: ignore[attr-defined]

        with patch("pipeline.cli.commands.suppressions.get_store", return_value=store):
            result = runner.invoke(app, ["suppressions", "list", "--repo", _REPO])

        assert result.exit_code == 0
        assert "never" in result.output

    def test_dated_suppression_shows_iso_expiry(self, tmp_path: Path) -> None:
        """A suppression with an expiry shows its ISO-formatted datetime."""
        expires = datetime(2030, 6, 15, 12, 0, 0, tzinfo=UTC)
        store = _make_store(tmp_path)
        sup = _make_suppression(expires_at=expires)
        store.write_suppression(sup)  # type: ignore[attr-defined]

        with patch("pipeline.cli.commands.suppressions.get_store", return_value=store):
            result = runner.invoke(app, ["suppressions", "list", "--repo", _REPO])

        assert result.exit_code == 0
        assert "2030-06-15" in result.output

    def test_header_row_is_printed(self, tmp_path: Path) -> None:
        """The list command prints a header row when suppressions exist."""
        store = _make_store(tmp_path)
        sup = _make_suppression()
        store.write_suppression(sup)  # type: ignore[attr-defined]

        with patch("pipeline.cli.commands.suppressions.get_store", return_value=store):
            result = runner.invoke(app, ["suppressions", "list", "--repo", _REPO])

        assert "ID" in result.output
        assert "FINDING_CLASS" in result.output
        assert "DECISION" in result.output

    def test_expired_suppression_is_not_listed(self, tmp_path: Path) -> None:
        """Suppressions whose expires_at is in the past do not appear."""
        store = _make_store(tmp_path)
        expired = _make_suppression(
            suppression_id="expired-sup",
            expires_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        store.write_suppression(expired)  # type: ignore[attr-defined]

        with patch("pipeline.cli.commands.suppressions.get_store", return_value=store):
            result = runner.invoke(app, ["suppressions", "list", "--repo", _REPO])

        assert result.exit_code == 0
        assert "No active suppressions" in result.output
        assert "expired-sup" not in result.output

    def test_multiple_suppressions_all_appear(self, tmp_path: Path) -> None:
        """All active suppressions are listed when multiple exist."""
        store = _make_store(tmp_path)
        for i in range(3):
            sup = _make_suppression(
                suppression_id=f"sup-{i:03d}",
                finding_class=f"class.{i}.",
            )
            store.write_suppression(sup)  # type: ignore[attr-defined]

        with patch("pipeline.cli.commands.suppressions.get_store", return_value=store):
            result = runner.invoke(app, ["suppressions", "list", "--repo", _REPO])

        assert result.exit_code == 0
        for i in range(3):
            assert f"sup-{i:03d}" in result.output


class TestExpireCommand:
    """Tests for `pipeline suppressions expire`."""

    def test_known_id_echoes_confirmation(self, tmp_path: Path) -> None:
        """expire prints a confirmation message for a valid suppression ID."""
        store = _make_store(tmp_path)
        sup = _make_suppression(suppression_id="sup-to-expire")
        store.write_suppression(sup)  # type: ignore[attr-defined]

        with patch("pipeline.cli.commands.suppressions.get_store", return_value=store):
            result = runner.invoke(
                app, ["suppressions", "expire", "sup-to-expire", "--repo", _REPO]
            )

        assert result.exit_code == 0
        assert "sup-to-expire" in result.output

    def test_unknown_id_exits_with_code_1(self, tmp_path: Path) -> None:
        """expire exits with code 1 when the suppression ID is not found."""
        store = _make_store(tmp_path)

        with patch("pipeline.cli.commands.suppressions.get_store", return_value=store):
            result = runner.invoke(
                app, ["suppressions", "expire", "does-not-exist", "--repo", _REPO]
            )

        assert result.exit_code == 1

    def test_unknown_id_prints_error_message(self, tmp_path: Path) -> None:
        """expire prints an error referencing the missing ID."""
        store = _make_store(tmp_path)

        with patch("pipeline.cli.commands.suppressions.get_store", return_value=store):
            result = runner.invoke(app, ["suppressions", "expire", "ghost-id", "--repo", _REPO])

        assert "ghost-id" in result.output
        assert "Error" in result.output

    def test_expire_sets_expires_at_on_disk(self, tmp_path: Path) -> None:
        """expire writes an updated suppression with expires_at set to now."""
        store = _make_store(tmp_path)
        sup = _make_suppression(suppression_id="sup-disk")
        store.write_suppression(sup)  # type: ignore[attr-defined]

        before = datetime.now(UTC)
        with patch("pipeline.cli.commands.suppressions.get_store", return_value=store):
            runner.invoke(app, ["suppressions", "expire", "sup-disk", "--repo", _REPO])
        after = datetime.now(UTC)

        updated = store.read_suppression("sup-disk")  # type: ignore[attr-defined]
        assert updated is not None
        assert updated.expires_at is not None
        assert before <= updated.expires_at <= after

    def test_expired_suppression_is_no_longer_active(self, tmp_path: Path) -> None:
        """After expire, is_active() returns False for the suppression."""
        store = _make_store(tmp_path)
        sup = _make_suppression(suppression_id="sup-deactivate")
        store.write_suppression(sup)  # type: ignore[attr-defined]

        with patch("pipeline.cli.commands.suppressions.get_store", return_value=store):
            runner.invoke(app, ["suppressions", "expire", "sup-deactivate", "--repo", _REPO])

        updated = store.read_suppression("sup-deactivate")  # type: ignore[attr-defined]
        assert updated is not None
        assert updated.is_active() is False

    def test_expire_does_not_affect_other_suppressions(self, tmp_path: Path) -> None:
        """Expiring one suppression leaves others untouched."""
        store = _make_store(tmp_path)
        store.write_suppression(_make_suppression(suppression_id="expire-me"))  # type: ignore[attr-defined]
        store.write_suppression(  # type: ignore[attr-defined]
            _make_suppression(suppression_id="keep-me", finding_class="other.")
        )

        with patch("pipeline.cli.commands.suppressions.get_store", return_value=store):
            runner.invoke(app, ["suppressions", "expire", "expire-me", "--repo", _REPO])

        kept = store.read_suppression("keep-me")  # type: ignore[attr-defined]
        assert kept is not None
        assert kept.expires_at is None
