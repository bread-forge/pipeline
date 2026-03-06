"""Smoke tests for GateApp — verifies the Textual TUI launches and mounts correctly.

These tests are skipped automatically when the ``textual`` package is not installed.
Textual is added as a dependency by the gate_app module PR; once merged these tests
will run in the standard suite.
"""

from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest

pytest.importorskip("textual")

from beads.types import ProposalBead  # noqa: E402
from textual.containers import Horizontal  # noqa: E402
from textual.widgets import Footer  # noqa: E402

from pipeline.gate.app import GateApp  # noqa: E402
from pipeline.gate.widgets import ProposalDetail, ProposalList  # noqa: E402


def _make_proposal(proposal_id: str = "prop-1") -> ProposalBead:
    return ProposalBead(
        proposal_id=proposal_id,
        cycle_id="cycle-1",
        repo="owner/repo",
        spec_hash="abc123",
        # Use a path that doesn't exist — _load_spec handles OSError gracefully.
        spec_path="/nonexistent/spec.json",
        status="pending",
    )


def _make_store() -> Mock:
    return Mock()


class TestGateAppLayout:
    """Smoke tests verifying GateApp launches and mounts the expected layout."""

    def test_two_pane_layout_mounts_with_empty_proposals(self) -> None:
        """App launches and the Horizontal#main-panes container is present."""
        store = _make_store()

        async def _run() -> None:
            app = GateApp(proposals=[], store=store)
            async with app.run_test() as pilot:
                await pilot.pause()
                main_panes = app.query_one("#main-panes", Horizontal)
                assert main_panes is not None

        asyncio.run(_run())

    def test_proposal_list_widget_mounts(self) -> None:
        """ProposalList is present in the DOM after mount."""
        store = _make_store()

        async def _run() -> None:
            app = GateApp(proposals=[], store=store)
            async with app.run_test() as pilot:
                await pilot.pause()
                proposal_list = app.query_one(ProposalList)
                assert proposal_list is not None

        asyncio.run(_run())

    def test_proposal_detail_widget_mounts(self) -> None:
        """ProposalDetail is present in the DOM after mount."""
        store = _make_store()

        async def _run() -> None:
            app = GateApp(proposals=[], store=store)
            async with app.run_test() as pilot:
                await pilot.pause()
                proposal_detail = app.query_one(ProposalDetail)
                assert proposal_detail is not None

        asyncio.run(_run())

    def test_footer_widget_mounts(self) -> None:
        """Footer is present in the DOM after mount."""
        store = _make_store()

        async def _run() -> None:
            app = GateApp(proposals=[], store=store)
            async with app.run_test() as pilot:
                await pilot.pause()
                footer = app.query_one(Footer)
                assert footer is not None

        asyncio.run(_run())

    def test_layout_mounts_with_proposals(self) -> None:
        """All layout widgets mount correctly when proposals are provided."""
        store = _make_store()
        proposals = [_make_proposal("prop-a"), _make_proposal("prop-b")]

        async def _run() -> None:
            app = GateApp(proposals=proposals, store=store)
            async with app.run_test() as pilot:
                await pilot.pause()
                assert app.query_one("#main-panes", Horizontal) is not None
                assert app.query_one(ProposalList) is not None
                assert app.query_one(ProposalDetail) is not None

        asyncio.run(_run())

    def test_proposal_list_is_inside_main_panes(self) -> None:
        """ProposalList is a descendant of #main-panes."""
        store = _make_store()

        async def _run() -> None:
            app = GateApp(proposals=[], store=store)
            async with app.run_test() as pilot:
                await pilot.pause()
                main_panes = app.query_one("#main-panes", Horizontal)
                children = list(main_panes.query(ProposalList))
                assert len(children) == 1

        asyncio.run(_run())

    def test_proposal_detail_is_inside_main_panes(self) -> None:
        """ProposalDetail is a descendant of #main-panes."""
        store = _make_store()

        async def _run() -> None:
            app = GateApp(proposals=[], store=store)
            async with app.run_test() as pilot:
                await pilot.pause()
                main_panes = app.query_one("#main-panes", Horizontal)
                children = list(main_panes.query(ProposalDetail))
                assert len(children) == 1

        asyncio.run(_run())
