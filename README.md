# pipeline

Pipeline orchestrator — cycle management CLI for bread-forge repos.

`pipeline` drives a structured, phase-gated development cycle (analysis → synthesis → gate → execution → verification) for a GitHub repository. Each cycle is tracked as a persistent bead, guarded by an exclusive flock-based lock to prevent concurrent runs, and auditable through a per-cycle JSONL event log. The CLI composes all four core modules into a single `pipeline` command.

## Install

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```sh
uv sync
```

The `pipeline` entry point is registered automatically:

```sh
uv run pipeline --help
```

## Usage

```sh
# Start a new cycle for a repo
pipeline cycle start --repo owner/repo --trigger "weekly audit"

# Check current phase and event summary
pipeline cycle status <cycle-id> --repo owner/repo

# Replay the full event log for a cycle
pipeline cycle replay <cycle-id> --repo owner/repo
```

State is stored under `~/.pipeline/`:

| Path | Contents |
|---|---|
| `~/.pipeline/beads/` | Cycle bead files (phase, timestamps) |
| `~/.pipeline/events/<owner>/<repo>/<cycle-id>.jsonl` | Per-cycle event log |
| `~/.pipeline/locks/` | flock files (one per repo) |

## Modules

| Module | Description |
|---|---|
| `pipeline.cycle` | `CyclePhase` enum, `CycleStateMachine` (pure phase-transition logic), and `write_phase_transition` for atomic bead persistence |
| `pipeline.lock` | `OrchestratorLock` — flock-based exclusive lock preventing concurrent cycles for the same repo |
| `pipeline.store` | `BeadStore` factory and `read_cycle`/`write_cycle` helpers; all bead I/O goes through this module |
| `pipeline.cli` | Typer app with `cycle start`, `cycle status`, and `cycle replay` subcommands |

## Cycle phases

```
analysis → synthesis → gate → execution → verification → complete
```

Each phase advances only when the required event type appears in the cycle's event log (e.g. `finding_added` completes `analysis`, `proposal_approved` completes `gate`).

## Tests

```sh
uv run pytest
```

## Lint

```sh
uv run ruff check src tests
```
