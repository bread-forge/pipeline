"""ProposalDetail widget — right pane showing proposal analysis sections."""

from __future__ import annotations

from typing import Any

from beads.types import ProposalBead
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import Label, Static

# Keys expected in the spec dict passed to ProposalDetail.
KEY_WHY_NOW = "why_now"
KEY_ACCEPTANCE_CRITERIA = "acceptance_criteria"
KEY_BLAST_RADIUS = "blast_radius"
KEY_SOURCE_FINDINGS = "source_findings"
KEY_PE_ASSESSMENT = "pe_assessment"

_SECTION_HEADINGS: list[tuple[str, str]] = [
    (KEY_WHY_NOW, "Why Now"),
    (KEY_ACCEPTANCE_CRITERIA, "Acceptance Criteria"),
    (KEY_BLAST_RADIUS, "Blast Radius"),
    (KEY_SOURCE_FINDINGS, "Source Findings"),
    (KEY_PE_ASSESSMENT, "PE Assessment"),
]


def _to_display_text(value: object) -> str:
    """Render a spec field value as a human-readable string."""
    if value is None:
        return "(none)"
    if isinstance(value, list):
        return "\n".join(f"• {item}" for item in value)
    return str(value)


class _Section(Static):
    """A labelled detail section (heading + body text)."""

    DEFAULT_CSS = """
    _Section {
        margin-bottom: 1;
        padding: 0 1;
        border: dashed $panel;
    }
    _Section > Label {
        text-style: bold;
        color: $accent;
    }
    """

    def __init__(self, heading: str, body: str) -> None:
        super().__init__()
        self._heading = heading
        self._body = body

    def compose(self) -> ComposeResult:
        yield Label(self._heading)
        yield Static(self._body)


class ProposalDetail(Widget):
    """Right pane that displays the full analysis for a selected proposal.

    Shows five sections sourced from the spec dict: why-now, acceptance
    criteria, blast radius, source findings, and PE assessment.

    Args:
        proposal: The :class:`~beads.types.ProposalBead` to display, or
            ``None`` to show an empty-selection placeholder.
        spec: Mapping of spec field keys to their values. Recognised keys are
            :data:`KEY_WHY_NOW`, :data:`KEY_ACCEPTANCE_CRITERIA`,
            :data:`KEY_BLAST_RADIUS`, :data:`KEY_SOURCE_FINDINGS`, and
            :data:`KEY_PE_ASSESSMENT`.  Missing keys render as ``"(none)"``.
    """

    DEFAULT_CSS = """
    ProposalDetail {
        height: 100%;
    }
    ProposalDetail > ScrollableContainer {
        height: 100%;
    }
    """

    def __init__(
        self,
        proposal: ProposalBead | None = None,
        spec: dict[str, Any] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._proposal = proposal
        self._spec: dict[str, Any] = spec or {}

    def compose(self) -> ComposeResult:
        if self._proposal is None:
            yield Static("No proposal selected.")
            return

        p = self._proposal
        with ScrollableContainer(), Vertical():
            yield Label(f"Proposal {p.proposal_id}  ·  {p.repo}  ·  {p.status.upper()}")
            for key, heading in _SECTION_HEADINGS:
                yield _Section(heading, _to_display_text(self._spec.get(key)))

    def update_proposal(
        self,
        proposal: ProposalBead | None,
        spec: dict[str, Any] | None = None,
    ) -> None:
        """Replace the displayed proposal and re-render the widget.

        Args:
            proposal: New proposal to display, or ``None`` to clear.
            spec: New spec dict; ``None`` clears all sections to ``"(none)"``.
        """
        self._proposal = proposal
        self._spec = spec or {}
        self.refresh(recompose=True)
