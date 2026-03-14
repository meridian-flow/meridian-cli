from pathlib import Path

import pytest

from meridian.lib.sync.install_config import ManagedSourceConfig, ManagedSourcesConfig, load_install_config
from meridian.lib.sync.install_config import write_install_config
from meridian.lib.sync.install_types import ItemRef


def test_managed_source_config_rejects_incompatible_kind_fields() -> None:
    with pytest.raises(ValueError, match="Git sources require 'url' and must not set 'path'"):
        ManagedSourceConfig(name="team", kind="git", path="./agents")

    with pytest.raises(ValueError, match="Path sources require 'path' and must not set 'url'"):
        ManagedSourceConfig(name="local", kind="path", url="https://example.com/repo.git")


def test_managed_source_config_rejects_noncanonical_rename_keys() -> None:
    with pytest.raises(ValueError, match="expected canonical 'agent:name' or 'skill:name'"):
        ManagedSourceConfig(
            name="team",
            kind="git",
            url="https://example.com/repo.git",
            rename={"reviewer-solid": "team-reviewer"},
        )


def test_load_install_config_roundtrips_multiple_sources(tmp_path: Path) -> None:
    config_path = tmp_path / ".meridian" / "agents.toml"
    config = ManagedSourcesConfig(
        sources=(
            ManagedSourceConfig(
                name="meridian-agents",
                kind="git",
                url="https://github.com/haowjy/meridian-agents.git",
                ref="main",
                items=(
                    ItemRef(kind="agent", name="dev-orchestrator"),
                    ItemRef(kind="skill", name="dev-workflow"),
                ),
                rename={"agent:dev-orchestrator": "team-orchestrator"},
            ),
            ManagedSourceConfig(
                name="local",
                kind="path",
                path="./tools/agents",
            ),
        )
    )

    write_install_config(config_path, config)
    loaded = load_install_config(config_path)

    assert loaded == config
