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


def test_managed_source_config_rejects_noncanonical_rename_keys() -> None:
    with pytest.raises(ValueError, match="expected canonical 'agent:name' or 'skill:name'"):
        SourceConfig(
            name="team",
            kind="git",
            url="https://example.com/repo.git",
            rename={"reviewer-solid": "team-reviewer"},
        )


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


def test_new_format_agents_skills_roundtrip(tmp_path: Path) -> None:
    config_path = tmp_path / ".meridian" / "agents.toml"
    config = SourcesConfig(
        sources=(
            SourceConfig(
                name="meridian-base",
                kind="git",
                url="https://github.com/haowjy/meridian-base.git",
                ref="main",
                agents=("__meridian-orchestrator", "__meridian-subagent"),
                skills=("__meridian-orchestration",),
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
    assert source.items is None  # migrated away


def test_both_items_and_agents_raises() -> None:
    with pytest.raises(ValueError, match="Cannot specify both"):
        SourceConfig(
            name="test",
            kind="git",
            url="https://example.com/repo.git",
            agents=("foo",),
            items=(ItemRef(kind="agent", name="bar"),),
        )


def test_effective_items_returns_none_when_no_filter() -> None:
    source = SourceConfig(name="test", kind="git", url="https://example.com/repo.git")
    assert source.effective_items is None


def test_effective_items_builds_refs_from_agents_and_skills() -> None:
    source = SourceConfig(
        name="test",
        kind="git",
        url="https://example.com/repo.git",
        agents=("a1", "a2"),
        skills=("s1",),
    )
    refs = source.effective_items
    assert refs is not None
    assert len(refs) == 3
    assert refs[0] == ItemRef(kind="agent", name="a1")
    assert refs[1] == ItemRef(kind="agent", name="a2")
    assert refs[2] == ItemRef(kind="skill", name="s1")


# ---------------------------------------------------------------------------
# SourceManifest — local overrides shared
# ---------------------------------------------------------------------------


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

    # all_sources should contain only the local version
    assert len(manifest.all_sources) == 1
    assert manifest.all_sources[0].ref == "my-branch"
    assert manifest.all_sources[0].agents == ("coder", "reviewer")

    # find_source returns local version
    found = manifest.find_source("team")
    assert found is not None
    assert found.ref == "my-branch"

    # file_for_source returns "local"
    assert manifest.file_for_source("team") == "local"

    # is_overridden is True
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
    # "b" should be the local version
    b = next(s for s in manifest.all_sources if s.name == "b")
    assert b.ref == "dev"


def test_manifest_without_local_override_reveals_shared() -> None:
    shared_source = SourceConfig(
        name="team",
        kind="git",
        url="https://team.git",
        ref="main",
    )
    local_source = SourceConfig(
        name="team",
        kind="git",
        url="https://team.git",
        ref="experiment",
    )
    manifest = SourceManifest(
        shared=SourcesConfig(sources=(shared_source,)),
        local=SourcesConfig(sources=(local_source,)),
    )

    # Remove only from local — shared base should become visible
    updated = SourceManifest(
        shared=manifest.shared,
        local=SourcesConfig(sources=()),
    )
    assert len(updated.all_sources) == 1
    assert updated.all_sources[0].ref == "main"
    assert updated.is_overridden("team") is False


def test_manifest_load_roundtrip_with_override(tmp_path: Path) -> None:
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
    assert len(loaded.all_sources) == 2  # "team" deduplicated
    assert loaded.find_source("team") is not None
    assert loaded.find_source("team").ref == "dev"  # type: ignore[union-attr]


def test_manifest_is_not_overridden_for_local_only_source() -> None:
    manifest = SourceManifest(
        shared=SourcesConfig(),
        local=SourcesConfig(sources=(SourceConfig(name="local-dev", kind="path", path="./dev"),)),
    )
    assert manifest.is_overridden("local-dev") is False
    assert manifest.file_for_source("local-dev") == "local"


def test_route_source_to_file_defaults_path_sources_to_shared() -> None:
    assert route_source_to_file() == "shared"


def test_route_source_to_file_uses_local_when_explicitly_requested() -> None:
    assert route_source_to_file(force_local=True) == "local"
