# pipeline

Pipeline orchestrator — dispatch repo-audit agents and manage analysis cycles from the command line.

The pipeline drives a multi-phase cycle (ANALYSIS → SYNTHESIS → GATE → EXECUTION → VERIFICATION) for each repository. It launches `repo-audit` agents as subprocesses, collects their findings into a `BeadStore`, and advances the cycle state machine when all agents complete. A trigger engine watches for GitHub PR merges or a daily schedule and fires the pipeline automatically. Proposals produced by the synthesis phase are reviewed interactively in a terminal UI before any execution takes place.

## Install

Requires Python 3.11+. Dependencies are managed with [uv](https://github.com/astral-sh/uv).

```
uv sync
```

Or with pip:

```
pip install -e .
```

The `beads` dependency is resolved from `https://github.com/bread-forge/beads.git`.

The `pipeline gate` command requires [Textual](https://github.com/Textualize/textual), which is not installed by default:

```
uv add textual
```

## Usage

### One-shot run

Dispatch agents against a repository and print a synthesis proposal list:

```
pipeline run --repo owner/repo
pipeline run --repo owner/repo --agents depth --agents coverage --path /path/to/repo
```

Agents default to the `analysis_agents` list in `~/.pipeline/config.yaml` when `--agents` is not passed.

### Watch mode

Poll continuously for a trigger event and fire the pipeline each time it fires:

```
pipeline watch --repo owner/repo --on pr_merge
pipeline watch --repo owner/repo --on daily --interval 300
```

Valid `--on` values: `pr_merge`, `daily`, `manual`.
`pr_merge` requires `GH_TOKEN` in the environment.
Press Ctrl-C to stop.

### Gate review

Open the interactive TUI to review pending proposals for a repository:

```
pipeline gate --repo owner/repo
pipeline gate --repo owner/repo --cycle <cycle-id>
```

The TUI shows a two-pane layout: the left pane lists proposals ordered by status (pending first), the right pane shows the full analysis for the selected proposal. Keyboard shortcuts:

| Key | Action |
|-----|--------|
| `a` | Approve the selected proposal |
| `r` | Reject with a required reason |
| `d` | Defer until a date (`YYYY-MM-DD`) |
| `?` | Show help overlay |
| `q` | Quit |

Each action updates the `ProposalBead` status in the store and appends a `GateDecision` event to the event log. No subprocess dispatch occurs during the gate phase in this milestone.

### Cycle management

```
pipeline cycle --help
```

## Configuration

Config lives at `~/.pipeline/config.yaml`:

```yaml
repos:
  owner/repo:
    triggers:
      - pr_merge
      - daily
    analysis_agents:
      - depth
      - coverage
```

## Module overview

| Module | Path | Description |
|--------|------|-------------|
| `config` | `src/pipeline/config/` | Reads and writes `~/.pipeline/config.yaml` using Pydantic models. |
| `dispatch` | `src/pipeline/dispatch/` | `AgentDispatcher` — runs `repo-audit` subprocesses, emits `AgentDispatched`/`AgentCompleted` events, and signals ANALYSIS→SYNTHESIS. |
| `cycle` | `src/pipeline/cycle/` | `CycleStateMachine` (phase transitions), `CyclePhase` enum, and bead write helpers. |
| `trigger` | `src/pipeline/trigger/` | `TriggerEngine` polling loop with `pr_merge`, `daily`, and `manual` trigger types. |
| `events` | `src/pipeline/events/` | `EventLog` and typed event dataclasses (`AgentDispatched`, `AgentCompleted`, `GateDecision`, …). |
| `store` | `src/pipeline/store/` | Thin wrappers around `BeadStore` for cycle and proposal persistence (`read_cycle`, `write_cycle`, `read_proposal`, `write_proposal`, `list_proposals`). |
| `lock` | `src/pipeline/lock/` | Orchestrator lock to prevent concurrent pipeline runs on the same repo. |
| `gate` | `src/pipeline/gate/` | Gate phase: `GateActions` (approve/reject/defer logic), `GateApp` (Textual TUI), and widgets (`ProposalList`, `ProposalDetail`, `ActionPrompt`). |
| `cli` | `src/pipeline/cli/` | Typer app wiring `run`, `watch`, `cycle`, and `gate` subcommands. |

## Tests

```
uv run pytest
```

Lint:

```
uv run ruff check src tests
```
