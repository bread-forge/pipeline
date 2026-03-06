"""Tests for pipeline.config — load_config and save_config."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from pipeline.config.loader import (
    PipelineConfig,
    RepoConfig,
    load_config,
    save_config,
)


class TestRepoConfig:
    """Tests for RepoConfig model defaults and validation."""

    def test_defaults_are_empty_lists(self) -> None:
        """RepoConfig with no arguments has empty triggers and analysis_agents."""
        cfg = RepoConfig()
        assert cfg.triggers == []
        assert cfg.analysis_agents == []

    def test_accepts_trigger_and_agent_lists(self) -> None:
        cfg = RepoConfig(triggers=["push", "schedule"], analysis_agents=["agent-a"])
        assert cfg.triggers == ["push", "schedule"]
        assert cfg.analysis_agents == ["agent-a"]

    def test_rejects_non_list_triggers(self) -> None:
        with pytest.raises(ValidationError):
            RepoConfig(triggers="push")  # type: ignore[arg-type]


class TestPipelineConfig:
    """Tests for PipelineConfig model defaults and validation."""

    def test_default_repos_is_empty_dict(self) -> None:
        cfg = PipelineConfig()
        assert cfg.repos == {}

    def test_accepts_repo_entries(self) -> None:
        cfg = PipelineConfig(
            repos={
                "owner/repo": RepoConfig(triggers=["push"], analysis_agents=["ag"]),
            }
        )
        assert "owner/repo" in cfg.repos
        assert cfg.repos["owner/repo"].triggers == ["push"]

    def test_model_validate_from_dict(self) -> None:
        raw = {
            "repos": {
                "org/svc": {
                    "triggers": ["schedule"],
                    "analysis_agents": ["bot-1", "bot-2"],
                }
            }
        }
        cfg = PipelineConfig.model_validate(raw)
        assert cfg.repos["org/svc"].analysis_agents == ["bot-1", "bot-2"]


class TestLoadConfig:
    """Tests for load_config()."""

    def test_returns_empty_config_when_file_missing(self, tmp_path: Path) -> None:
        """Missing config file yields an empty PipelineConfig, not an error."""
        cfg = load_config(config_path=tmp_path / "config.yaml")
        assert isinstance(cfg, PipelineConfig)
        assert cfg.repos == {}

    def test_returns_empty_config_for_empty_file(self, tmp_path: Path) -> None:
        """Empty YAML file is treated as an empty config."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("")
        cfg = load_config(config_path=config_path)
        assert cfg.repos == {}

    def test_loads_single_repo(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "repos:\n"
            "  owner/repo:\n"
            "    triggers:\n"
            "      - push\n"
            "    analysis_agents:\n"
            "      - agent-1\n"
        )
        cfg = load_config(config_path=config_path)
        assert "owner/repo" in cfg.repos
        assert cfg.repos["owner/repo"].triggers == ["push"]
        assert cfg.repos["owner/repo"].analysis_agents == ["agent-1"]

    def test_loads_multiple_repos(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "repos:\n"
            "  alpha/svc:\n"
            "    triggers: [push]\n"
            "    analysis_agents: []\n"
            "  beta/svc:\n"
            "    triggers: [schedule]\n"
            "    analysis_agents: [bot]\n"
        )
        cfg = load_config(config_path=config_path)
        assert len(cfg.repos) == 2
        assert cfg.repos["beta/svc"].triggers == ["schedule"]

    def test_repo_with_no_triggers_defaults_to_empty(self, tmp_path: Path) -> None:
        """A repo block with only analysis_agents gets an empty triggers list."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "repos:\n"
            "  owner/repo:\n"
            "    analysis_agents:\n"
            "      - bot\n"
        )
        cfg = load_config(config_path=config_path)
        assert cfg.repos["owner/repo"].triggers == []

    def test_repo_with_no_agents_defaults_to_empty(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "repos:\n"
            "  owner/repo:\n"
            "    triggers:\n"
            "      - push\n"
        )
        cfg = load_config(config_path=config_path)
        assert cfg.repos["owner/repo"].analysis_agents == []

    def test_raises_on_invalid_yaml(self, tmp_path: Path) -> None:
        """Malformed YAML raises yaml.YAMLError."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("repos: {\n  bad yaml")
        with pytest.raises(yaml.YAMLError):
            load_config(config_path=config_path)

    def test_raises_on_wrong_field_type(self, tmp_path: Path) -> None:
        """Valid YAML but wrong types raises a validation error."""
        config_path = tmp_path / "config.yaml"
        # triggers must be a list, not a string
        config_path.write_text(
            "repos:\n"
            "  owner/repo:\n"
            "    triggers: push\n"
        )
        with pytest.raises(ValidationError):
            load_config(config_path=config_path)

    def test_empty_repos_block(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        config_path.write_text("repos: {}\n")
        cfg = load_config(config_path=config_path)
        assert cfg.repos == {}


class TestSaveConfig:
    """Tests for save_config()."""

    def test_creates_file_at_given_path(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        save_config(PipelineConfig(), config_path=config_path)
        assert config_path.exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        config_path = tmp_path / "nested" / "dir" / "config.yaml"
        save_config(PipelineConfig(), config_path=config_path)
        assert config_path.exists()

    def test_written_file_is_valid_yaml(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        save_config(PipelineConfig(), config_path=config_path)
        raw = yaml.safe_load(config_path.read_text())
        # An empty PipelineConfig serialises repos as an empty dict.
        assert raw == {"repos": {}}

    def test_round_trip_preserves_all_fields(self, tmp_path: Path) -> None:
        """load_config(save_config(cfg)) returns an equivalent config."""
        config_path = tmp_path / "config.yaml"
        original = PipelineConfig(
            repos={
                "owner/repo": RepoConfig(
                    triggers=["push", "schedule"],
                    analysis_agents=["agent-1", "agent-2"],
                )
            }
        )
        save_config(original, config_path=config_path)
        reloaded = load_config(config_path=config_path)
        assert reloaded.repos["owner/repo"].triggers == ["push", "schedule"]
        assert reloaded.repos["owner/repo"].analysis_agents == ["agent-1", "agent-2"]

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """Saving twice replaces the previous content."""
        config_path = tmp_path / "config.yaml"
        first = PipelineConfig(
            repos={"owner/repo": RepoConfig(triggers=["push"])}
        )
        save_config(first, config_path=config_path)

        second = PipelineConfig(
            repos={"owner/repo": RepoConfig(triggers=["schedule"])}
        )
        save_config(second, config_path=config_path)

        reloaded = load_config(config_path=config_path)
        assert reloaded.repos["owner/repo"].triggers == ["schedule"]

    def test_empty_config_round_trip(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        save_config(PipelineConfig(), config_path=config_path)
        cfg = load_config(config_path=config_path)
        assert cfg.repos == {}
