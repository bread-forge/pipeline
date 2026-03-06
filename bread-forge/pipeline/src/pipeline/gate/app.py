"""GateApp — Textual TUI for reviewing and acting on gate proposals."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from time import monotonic
from typing import Any

from beads.store import BeadStore
from beads.types import ProposalBead
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import Footer, Static

from pipeline.events.log import EventLog
from pipeline.gate.actions import GateActions
from pipeline.gate.widgets import ActionPrompt, ProposalDetail, ProposalList

HEADLESS_TEST_EXIT_DELAY = 2.0

_HELP_TEXT = """\
 Keyboard Shortcuts
 ══════════════════

 a   Approve selected proposal (confirm required)
 r   Reject selected proposal  (reason required)
 d   Defer selected proposal   (date YYYY-MM-DD required)

 ?   Show this help overlay
 q   Quit

 Press Escape or ? to close.
"""


class _HelpScreen(ModalScreen[None]):
    """Modal overlay listing available keyboard shortcuts."""

    BINDINGS = [
        Binding("escape,question_mark,q", "dismiss_help", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Static(_HELP_TEXT, id="help-content")

    def action_dismiss_help(self) -> None:
        self.dismiss()


class GateApp(App[None]):
    """Textual TUI for reviewing and gating pipeline proposals.

    Displays a two-pane horizontal layout: the left pane shows a scrollable,
    priority-ordered list of proposals; the right pane shows the full analysis
    for the currently selected proposal.

    Keybindings ``a``, ``r``, and ``d`` drive approve, reject, and defer
    actions via :class:`~pipeline.gate.actions.GateActions`.  Approve requires
    a confirmation click in :class:`~pipeline.gate.widgets.ActionPrompt`;
    reject and defer additionally collect a reason or date.

    Args:
        proposals: Proposals to display.  If non-empty the first item is
            pre-selected on startup.
        store: BeadStore used by GateActions to persist decisions.
        event_log: Optional EventLog for recording GateDecision events.
        headless_test: When ``True`` the app exits automatically after
            :data:`HEADLESS_TEST_EXIT_DELAY` seconds.  Intended for CI
            smoke tests that verify the TUI starts without crashing.
    """

    BINDINGS = [
        Binding("a", "approve", "Approve"),
        Binding("r", "reject", "Reject"),
        Binding("d", "defer", "Defer"),
        Binding("question_mark", "help", "Help"),
        Binding("q", "quit", "Quit"),
    ]

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-panes {
        height: 1fr;
        layout: horizontal;
    }

    ProposalList {
        width: 35%;
        border: solid $panel;
    }

    ProposalDetail {
        width: 65%;
        border: solid $panel;
    }

    #help-content {
        width: 50;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: double $accent;
    }
    """

    def __init__(
        self,
        proposals: list[ProposalBead],
        store: BeadStore,
        event_log: EventLog | None = None,
        headless_test: bool = False,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._proposals = proposals
        self._actions = GateActions(store, event_log)
        self._headless_test = headless_test
        self._selected: ProposalBead | None = proposals[0] if proposals else None
        self._selection_time: float = monotonic()

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-panes"):
            yield ProposalList(self._proposals)
            yield ProposalDetail(
                self._selected,
                spec=_load_spec(self._selected) if self._selected else None,
            )
        yield ActionPrompt("", id="action-prompt")
        yield Footer()

    def on_mount(self) -> None:
        if self._headless_test:
            self.set_timer(HEADLESS_TEST_EXIT_DELAY, self.exit)

    # ------------------------------------------------------------------
    # Proposal selection
    # ------------------------------------------------------------------

    def on_proposal_list_selected(self, event: ProposalList.Selected) -> None:
        self._selected = event.proposal
        self._selection_time = monotonic()
        self.query_one(ProposalDetail).update_proposal(
            event.proposal,
            spec=_load_spec(event.proposal),
        )

    # ------------------------------------------------------------------
    # Key actions
    # ------------------------------------------------------------------

    def action_approve(self) -> None:
        if self._selected is None:
            return
        self.query_one(ActionPrompt).show_approve(self._selected.proposal_id)

    def action_reject(self) -> None:
        if self._selected is None:
            return
        self.query_one(ActionPrompt).show_reject(self._selected.proposal_id)

    def action_defer(self) -> None:
        if self._selected is None:
            return
        self.query_one(ActionPrompt).show_defer(self._selected.proposal_id)

    def action_help(self) -> None:
        self.push_screen(_HelpScreen())

    # ------------------------------------------------------------------
    # ActionPrompt responses
    # ------------------------------------------------------------------

    def on_action_prompt_submitted(self, event: ActionPrompt.Submitted) -> None:
        review_secs = monotonic() - self._selection_time
        if event.action == "approve":
            self._actions.approve(event.proposal_id, review_secs)
        elif event.action == "reject":
            self._actions.reject(event.proposal_id, event.reason, review_secs)
        elif event.action == "defer":
            self._actions.defer(
                event.proposal_id,
                _date_to_utc_datetime(event.defer_until),  # type: ignore[arg-type]
                review_secs,
            )

    def on_action_prompt_cancelled(self, _event: ActionPrompt.Cancelled) -> None:
        # The prompt hides itself; nothing more to do here.
        pass


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _load_spec(proposal: ProposalBead) -> dict[str, Any]:
    """Read the spec JSON from ``proposal.spec_path``.

    Returns an empty dict if the file is missing or not valid JSON.
    """
    try:
        with open(proposal.spec_path) as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _date_to_utc_datetime(d: date) -> datetime:
    """Convert a :class:`date` to a UTC-aware midnight :class:`datetime`."""
    return datetime(d.year, d.month, d.day, tzinfo=UTC)
