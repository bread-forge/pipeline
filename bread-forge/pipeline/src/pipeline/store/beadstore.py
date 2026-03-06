"""BeadStore wiring for the pipeline package.

Provides a factory and cycle-specific helpers so callers never import from
beads directly — all store access goes through this module.
"""

from pathlib import Path

from beads.store import BeadStore
from beads.types import CycleBead

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
