from pathlib import Path

import pytest

from meridian.lib.install.config import (
    SourceConfig,
    SourceManifest,
    SourcesConfig,
    load_source_manifest,
    load_sources_config,
    route_source_to_file,
    write_source_manifest,
    write_sources_config,
)
from meridian.lib.install.types import ItemRef


def test_managed_source_config_rejects_incompatible_kind_fields() -> None:
    with pytest.raises(ValueError, match="Git sources require 'url' and must not set 'path'"):
        SourceConfig(name="team", kind="git", path="./agents")

    with pytest.raises(ValueError, match="Path sources require 'path' and must not set 'url'"):
        SourceConfig(name="local", kind="path", url="https://example.com/repo.git")


def test_load_sources_config_roundtrips_multiple_sources(tmp_path: Path) -> None:
    config_path = tmp_path / ".meridian" / "agents.toml"
    config = SourcesConfig(
        sources=(
            SourceConfig(
                name="meridian-base",
                kind="git",
                url="https://github.com/haowjy/meridian-base.git",
                ref="main",
                agents=("dev-orchestrator",),
                skills=("dev-workflow",),
                rename={"agent:dev-orchestrator": "team-orchestrator"},
            ),
            SourceConfig(
                name="local",
                kind="path",
                path="./tools/agents",
            ),
        )
    )

    write_sources_config(config_path, config)
    loaded = load_sources_config(config_path)

    assert loaded == config


def test_old_format_auto_migrates_on_read(tmp_path: Path) -> None:
    config_path = tmp_path / ".meridian" / "agents.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "[[sources]]\n"
        'name = "test"\n'
        'kind = "git"\n'
        'url = "https://example.com/repo.git"\n'
        "items = [\n"
        '  { kind = "agent", name = "orchestrator" },\n'
        '  { kind = "skill", name = "workflow" },\n'
        "]\n",
        encoding="utf-8",
    )

    loaded = load_sources_config(config_path)
    source = loaded.sources[0]

    assert source.agents == ("orchestrator",)
    assert source.skills == ("workflow",)
    assert source.items is None


def test_both_items_and_agents_raises() -> None:
    with pytest.raises(ValueError, match="Cannot specify both"):
        SourceConfig(
            name="test",
            kind="git",
            url="https://example.com/repo.git",
            agents=("foo",),
            items=(ItemRef(kind="agent", name="bar"),),
        )


def test_effective_items_maps_agents_and_skills_and_none_when_unfiltered() -> None:
    unfiltered = SourceConfig(name="test", kind="git", url="https://example.com/repo.git")
    assert unfiltered.effective_items is None

    filtered = SourceConfig(
        name="test",
        kind="git",
        url="https://example.com/repo.git",
        agents=("a1", "a2"),
        skills=("s1",),
    )
    assert filtered.effective_items == (
        ItemRef(kind="agent", name="a1"),
        ItemRef(kind="agent", name="a2"),
        ItemRef(kind="skill", name="s1"),
    )


def test_manifest_local_overrides_shared_source() -> None:
    shared_source = SourceConfig(
        name="team",
        kind="git",
        url="https://github.com/org/team.git",
        ref="main",
        agents=("coder",),
    )
    local_source = SourceConfig(
        name="team",
        kind="git",
        url="https://github.com/org/team.git",
        ref="my-branch",
        agents=("coder", "reviewer"),
    )
    manifest = SourceManifest(
        shared=SourcesConfig(sources=(shared_source,)),
        local=SourcesConfig(sources=(local_source,)),
    )

    assert len(manifest.all_sources) == 1
    assert manifest.all_sources[0].ref == "my-branch"
    assert manifest.find_source("team") is not None
    assert manifest.find_source("team").ref == "my-branch"  # type: ignore[union-attr]
    assert manifest.file_for_source("team") == "local"
    assert manifest.is_overridden("team") is True


def test_manifest_all_sources_merges_without_duplicates() -> None:
    shared = SourcesConfig(
        sources=(
            SourceConfig(name="a", kind="git", url="https://a.git"),
            SourceConfig(name="b", kind="git", url="https://b.git"),
        )
    )
    local = SourcesConfig(
        sources=(
            SourceConfig(name="b", kind="git", url="https://b.git", ref="dev"),
            SourceConfig(name="c", kind="path", path="./c"),
        )
    )
    manifest = SourceManifest(shared=shared, local=local)

    names = [s.name for s in manifest.all_sources]
    assert names == ["a", "b", "c"]
    b = next(s for s in manifest.all_sources if s.name == "b")
    assert b.ref == "dev"


def test_manifest_load_roundtrip_with_override_and_route_controls(tmp_path: Path) -> None:
    shared_path = tmp_path / "agents.toml"
    local_path = tmp_path / "agents.local.toml"

    shared = SourcesConfig(
        sources=(SourceConfig(name="team", kind="git", url="https://team.git", ref="main"),)
    )
    local = SourcesConfig(
        sources=(
            SourceConfig(name="team", kind="git", url="https://team.git", ref="dev"),
            SourceConfig(name="local-dev", kind="path", path="./dev"),
        )
    )
    original = SourceManifest(shared=shared, local=local)

    write_source_manifest(shared_path, local_path, original)
    loaded = load_source_manifest(shared_path, local_path)

    assert loaded.shared == original.shared
    assert loaded.local == original.local
    assert len(loaded.all_sources) == 2
    assert loaded.find_source("team") is not None
    assert loaded.find_source("team").ref == "dev"  # type: ignore[union-attr]
    assert loaded.is_overridden("local-dev") is False
    assert route_source_to_file() == "shared"
    assert route_source_to_file(force_local=True) == "local"
