"""Config loader — reads and writes ~/.pipeline/config.yaml.

The on-disk format is:

    repos:
      owner/repo:
        triggers:
          - push
          - schedule
        analysis_agents:
          - agent-slug-1
          - agent-slug-2

:func:`load_config` returns a validated :class:`PipelineConfig`.  Callers that
need to persist changes use :func:`save_config`.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

DEFAULT_CONFIG_PATH: Path = Path.home() / ".pipeline" / "config.yaml"


class RepoConfig(BaseModel):
    """Per-repo configuration block."""

    triggers: list[str] = Field(default_factory=list)
    analysis_agents: list[str] = Field(default_factory=list)


class PipelineConfig(BaseModel):
    """Root configuration object returned by :func:`load_config`."""

    repos: dict[str, RepoConfig] = Field(default_factory=dict)


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> PipelineConfig:
    """Read and validate the pipeline config from *config_path*.

    Returns an empty :class:`PipelineConfig` when the file does not exist or
    is empty.

    Args:
        config_path: Path to the YAML config file.  Defaults to
            ``~/.pipeline/config.yaml``.

    Returns:
        A validated :class:`PipelineConfig` instance.

    Raises:
        ValueError: When the YAML parses successfully but fails Pydantic
            validation (e.g. wrong field types).
        yaml.YAMLError: When the file content is not valid YAML.
    """
    if not config_path.exists():
        return PipelineConfig()

    raw = yaml.safe_load(config_path.read_text())
    if raw is None:
        # File exists but is empty.
        return PipelineConfig()

    return PipelineConfig.model_validate(raw)


def save_config(
    config: PipelineConfig,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> None:
    """Serialise *config* to *config_path* as YAML.

    Creates parent directories if they do not already exist.

    Args:
        config: The config object to persist.
        config_path: Destination path.  Defaults to
            ``~/.pipeline/config.yaml``.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.dump(config.model_dump(), default_flow_style=False))
