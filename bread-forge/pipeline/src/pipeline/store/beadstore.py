"""BeadStore wiring for the pipeline package.

Provides a factory and cycle-specific helpers so callers never import from
beads directly — all store access goes through this module.
"""

from pathlib import Path

from beads.store import BeadStore
from beads.types import CycleBead, ProposalBead

# Default location for all pipeline bead data.
BEADS_DIR: Path = Path.home() / ".pipeline" / "beads"


def get_store(repo: str, beads_dir: Path = BEADS_DIR) -> BeadStore:
    """Return a BeadStore rooted at *beads_dir* for the given *repo*.

    Args:
        repo: GitHub repository in ``owner/name`` format (e.g. ``"acme/api"``).
        beads_dir: Base directory for all bead files.  Defaults to
            ``~/.pipeline/beads/``.  Override in tests to keep state off disk.

    Returns:
        A configured :class:`beads.store.BeadStore` instance.
    """
    return BeadStore(beads_dir, repo)


def read_cycle(store: BeadStore, cycle_id: str) -> CycleBead | None:
    """Read a :class:`~beads.types.CycleBead` by its ID.

    Args:
        store: The store to read from.
        cycle_id: Unique identifier for the cycle.

    Returns:
        The deserialized ``CycleBead``, or ``None`` if no bead exists for
        *cycle_id*.
    """
    return store.read_cycle(cycle_id)


def write_cycle(store: BeadStore, bead: CycleBead) -> None:
    """Persist a :class:`~beads.types.CycleBead` to the store atomically.

    Args:
        store: The store to write to.
        bead: The cycle bead to serialize and save.
    """
    store.write_cycle(bead)


def write_proposal(store: BeadStore, bead: ProposalBead) -> None:
    """Persist a :class:`~beads.types.ProposalBead` to the store atomically.

    Args:
        store: The store to write to.
        bead: The proposal bead to serialize and save.
    """
    store.write_proposal(bead)


def read_proposal(store: BeadStore, proposal_id: str) -> ProposalBead | None:
    """Read a :class:`~beads.types.ProposalBead` by its ID.

    Args:
        store: The store to read from.
        proposal_id: Unique identifier for the proposal.

    Returns:
        The deserialized ``ProposalBead``, or ``None`` if no bead exists for
        *proposal_id*.
    """
    return store.read_proposal(proposal_id)


def list_proposals(
    store: BeadStore,
    repo: str,
    cycle_id: str | None = None,
) -> list[ProposalBead]:
    """List :class:`~beads.types.ProposalBead` objects for *repo*.

    Args:
        store: The store to read from.
        repo: GitHub repository in ``owner/name`` format.  Only proposals
            whose ``repo`` field matches are returned.
        cycle_id: When provided, further restricts results to proposals
            whose ``cycle_id`` field matches.

    Returns:
        A list of matching ``ProposalBead`` objects (may be empty).
    """
    proposals = store.list_proposals(repo=repo)
    if cycle_id is not None:
        proposals = [p for p in proposals if p.cycle_id == cycle_id]
    return proposals
