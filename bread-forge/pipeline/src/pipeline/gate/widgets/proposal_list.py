"""ProposalList widget — scrollable, priority-ordered list of pending proposals."""

from __future__ import annotations

from beads.types import ProposalBead
from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView

# Pending proposals surface first; terminal statuses sink to the bottom.
_STATUS_PRIORITY: dict[str, int] = {
    "pending": 0,
    "deferred": 1,
    "approved": 2,
    "rejected": 3,
    "dispatched": 4,
    "verified": 5,
    "failed": 6,
}


def _sort_key(proposal: ProposalBead) -> tuple[int, float]:
    """Sort key: status priority ascending, then creation time ascending."""
    return (
        _STATUS_PRIORITY.get(proposal.status, 99),
        proposal.created_at.timestamp(),
    )


class _ProposalItem(ListItem):
    """A single row in the ProposalList."""

    def __init__(self, proposal: ProposalBead) -> None:
        super().__init__()
        self.proposal = proposal

    def compose(self) -> ComposeResult:
        short_id = self.proposal.proposal_id[:8]
        status = self.proposal.status.upper()
        yield Label(f"[{status}] {short_id}  {self.proposal.repo}")


class ProposalList(Widget):
    """Scrollable list of proposals ordered by status priority then creation time.

    Emits a :class:`ProposalList.Selected` message whenever the user navigates
    to a different proposal row.

    Args:
        proposals: Proposals to display. They are sorted internally — callers
            need not pre-sort.
    """

    DEFAULT_CSS = """
    ProposalList {
        height: 100%;
    }
    ProposalList > ListView {
        height: 100%;
    }
    """

    class Selected(Message):
        """Posted when the user highlights a proposal row."""

        def __init__(self, proposal: ProposalBead) -> None:
            super().__init__()
            self.proposal = proposal

    def __init__(self, proposals: list[ProposalBead], **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._proposals: list[ProposalBead] = sorted(proposals, key=_sort_key)

    def compose(self) -> ComposeResult:
        yield ListView(*[_ProposalItem(p) for p in self._proposals])

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        if isinstance(event.item, _ProposalItem):
            self.post_message(self.Selected(event.item.proposal))
