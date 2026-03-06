# pipeline

Pipeline orchestrator — dispatch repo-audit agents and manage analysis cycles from the command line.

The pipeline drives a multi-phase cycle (ANALYSIS → SYNTHESIS → GATE → EXECUTION → VERIFICATION) for each repository. It launches `repo-audit` agents as subprocesses, collects their findings into a `BeadStore`, and advances the cycle state machine when all agents complete. A trigger engine watches for GitHub PR merges or a daily schedule and fires the pipeline automatically.

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
|---|---|---|
| `config` | `src/pipeline/config/` | Reads and writes `~/.pipeline/config.yaml` using Pydantic models. |
| `dispatch` | `src/pipeline/dispatch/` | `AgentDispatcher` — runs `repo-audit` subprocesses, emits `AgentDispatched`/`AgentCompleted` events, and signals ANALYSIS→SYNTHESIS. |
| `cycle` | `src/pipeline/cycle/` | `CycleStateMachine` (phase transitions), `CyclePhase` enum, and bead write helpers. |
| `trigger` | `src/pipeline/trigger/` | `TriggerEngine` polling loop with `pr_merge`, `daily`, and `manual` trigger types. |
| `events` | `src/pipeline/events/` | `EventLog` and typed event dataclasses (`AgentDispatched`, `AgentCompleted`, …). |
| `store` | `src/pipeline/store/` | Thin wrappers around `BeadStore` for cycle and finding persistence. |
| `lock` | `src/pipeline/lock/` | Orchestrator lock to prevent concurrent pipeline runs on the same repo. |
| `cli` | `src/pipeline/cli/` | Typer app wiring `run`, `watch`, and `cycle` subcommands. |

## Tests

```
uv run pytest
```

Lint:

```
uv run ruff check src tests
```
