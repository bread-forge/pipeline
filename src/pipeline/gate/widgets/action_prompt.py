"""ActionPrompt widget — inline form for gate approval, rejection, and deferral."""

from __future__ import annotations

from datetime import date

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input, Label

_DATE_FORMAT = "%Y-%m-%d"
_DATE_PLACEHOLDER = "YYYY-MM-DD"

# Action names used in Submitted.action
ACTION_APPROVE = "approve"
ACTION_REJECT = "reject"
ACTION_DEFER = "defer"


def _parse_iso_date(raw: str) -> date | None:
    """Parse a YYYY-MM-DD string. Returns None if the format is invalid."""
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


class ActionPrompt(Widget):
    """Inline form that collects the extra input required for a gate action.

    The widget is hidden by default. Call one of the ``show_*`` methods to
    configure it for a specific action and make it visible.  Call
    :meth:`hide` to dismiss it programmatically.

    * **approve** — confirmation only; no text input required.
    * **reject** — requires a non-empty reason string.
    * **defer** — requires a valid ``YYYY-MM-DD`` deferral date.

    On confirmation the widget posts :class:`ActionPrompt.Submitted` and
    hides itself. On cancellation it posts :class:`ActionPrompt.Cancelled`
    and hides itself.

    Args:
        proposal_id: ID of the proposal this prompt is acting on.
    """

    DEFAULT_CSS = """
    ActionPrompt {
        height: auto;
        display: none;
        border: solid $accent;
        padding: 1;
    }
    ActionPrompt.-visible {
        display: block;
    }
    ActionPrompt Horizontal {
        height: auto;
        margin-top: 1;
    }
    ActionPrompt Button {
        margin-right: 1;
    }
    """

    class Submitted(Message):
        """Posted when the user confirms the action.

        Attributes:
            proposal_id: The proposal this decision targets.
            action: One of ``"approve"``, ``"reject"``, or ``"defer"``.
            reason: Non-empty only for ``"reject"`` actions.
            defer_until: Non-``None`` only for ``"defer"`` actions.
        """

        def __init__(
            self,
            proposal_id: str,
            action: str,
            reason: str = "",
            defer_until: date | None = None,
        ) -> None:
            super().__init__()
            self.proposal_id = proposal_id
            self.action = action
            self.reason = reason
            self.defer_until = defer_until

    class Cancelled(Message):
        """Posted when the user cancels the action prompt.

        Attributes:
            proposal_id: The proposal the cancelled action targeted.
        """

        def __init__(self, proposal_id: str) -> None:
            super().__init__()
            self.proposal_id = proposal_id

    def __init__(self, proposal_id: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._proposal_id = proposal_id
        self._action = ACTION_APPROVE

    @property
    def proposal_id(self) -> str:
        """The ID of the proposal currently targeted by this prompt."""
        return self._proposal_id

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("", id="prompt-label")
            yield Input(placeholder="", id="prompt-input")
            with Horizontal():
                yield Button("Confirm", variant="success", id="btn-confirm")
                yield Button("Cancel", variant="error", id="btn-cancel")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_approve(self, proposal_id: str) -> None:
        """Display the prompt configured for an approval action.

        Args:
            proposal_id: ID of the proposal to approve.
        """
        self._proposal_id = proposal_id
        self._action = ACTION_APPROVE
        self._configure("Approve this proposal?", input_visible=False)
        self._set_visible(True)

    def show_reject(self, proposal_id: str) -> None:
        """Display the prompt configured for a rejection action.

        Args:
            proposal_id: ID of the proposal to reject.
        """
        self._proposal_id = proposal_id
        self._action = ACTION_REJECT
        self._configure("Rejection reason:", input_visible=True, placeholder="Reason…")
        self._set_visible(True)

    def show_defer(self, proposal_id: str) -> None:
        """Display the prompt configured for a deferral action.

        Args:
            proposal_id: ID of the proposal to defer.
        """
        self._proposal_id = proposal_id
        self._action = ACTION_DEFER
        self._configure(
            f"Defer until ({_DATE_PLACEHOLDER}):",
            input_visible=True,
            placeholder=_DATE_PLACEHOLDER,
        )
        self._set_visible(True)

    def hide(self) -> None:
        """Hide the prompt and clear any pending input."""
        self._set_visible(False)
        self.query_one("#prompt-input", Input).value = ""

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-confirm":
            self._handle_confirm()
        elif event.button.id == "btn-cancel":
            self._handle_cancel()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _handle_confirm(self) -> None:
        input_widget = self.query_one("#prompt-input", Input)
        raw = input_widget.value.strip()

        if self._action == ACTION_APPROVE:
            self.post_message(self.Submitted(self._proposal_id, action=ACTION_APPROVE))
            self.hide()
        elif self._action == ACTION_REJECT:
            if not raw:
                input_widget.focus()
                return
            self.post_message(self.Submitted(self._proposal_id, action=ACTION_REJECT, reason=raw))
            self.hide()
        elif self._action == ACTION_DEFER:
            parsed = _parse_iso_date(raw)
            if parsed is None:
                input_widget.focus()
                return
            self.post_message(
                self.Submitted(self._proposal_id, action=ACTION_DEFER, defer_until=parsed)
            )
            self.hide()

    def _handle_cancel(self) -> None:
        self.hide()
        self.post_message(self.Cancelled(self._proposal_id))

    def _configure(self, label: str, input_visible: bool, placeholder: str = "") -> None:
        self.query_one("#prompt-label", Label).update(label)
        input_widget = self.query_one("#prompt-input", Input)
        input_widget.placeholder = placeholder
        input_widget.display = input_visible
        if input_visible:
            input_widget.value = ""
            input_widget.focus()

    def _set_visible(self, visible: bool) -> None:
        if visible:
            self.add_class("-visible")
        else:
            self.remove_class("-visible")
