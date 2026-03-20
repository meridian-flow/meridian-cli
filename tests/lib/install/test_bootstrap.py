from pathlib import Path

import pytest

from meridian.lib.install.bootstrap import (
    ensure_bootstrap_assets,
    ensure_bootstrap_source_manifest,
    plan_bootstrap_assets,
    planned_bootstrap_agent_names,
)
from meridian.lib.install.config import (
    SourceConfig,
    SourceManifest,
    SourcesConfig,
    load_sources_config,
    write_sources_config,
)
from meridian.lib.install.engine import reconcile_sources
from meridian.lib.install.lock import read_lock, write_lock
from meridian.lib.state.paths import resolve_state_paths


def _write_source_tree(source_root: Path, *, agent_name: str) -> None:
    (source_root / "agents").mkdir(parents=True, exist_ok=True)
    (source_root / "agents" / f"{agent_name}.md").write_text(
        f"---\nname: {agent_name}\ndescription: Test agent\nmodel: gpt-5.3-codex\n---\nBody\n",
        encoding="utf-8",
    )


def test_ensure_bootstrap_assets_reinstalls_from_locked_source(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source_root = tmp_path / "source"
    _write_source_tree(source_root, agent_name="__meridian-subagent")

    paths = resolve_state_paths(repo_root)
    config = SourcesConfig(
        sources=(
            SourceConfig(
                name="local",
                kind="path",
                path=source_root.as_posix(),
            ),
        )
    )
    write_sources_config(paths.agents_manifest_path, config)

    lock = read_lock(paths.agents_lock_path)
    reconcile_sources(
        repo_root=repo_root,
        sources=config.sources,
        lock=lock,
        agents_cache_dir=paths.agents_cache_dir,
    )
    write_lock(paths.agents_lock_path, lock)

    installed_path = repo_root / ".agents" / "agents" / "__meridian-subagent.md"
    installed_path.unlink()

    plan = plan_bootstrap_assets(
        repo_root=repo_root,
        agent_names=("__meridian-subagent",),
    )
    ensure_bootstrap_assets(repo_root=repo_root, plan=plan)

    assert installed_path.is_file()
    lock_after = read_lock(paths.agents_lock_path)
    assert "agent:__meridian-subagent" in lock_after.items
    assert load_sources_config(paths.agents_manifest_path).sources[0].name == "local"


def test_ensure_bootstrap_assets_bootstraps_missing_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source_root = tmp_path / "bootstrap-source"
    _write_source_tree(source_root, agent_name="__meridian-subagent")

    def fake_ensure_bootstrap_source_manifest(
        *,
        manifest: SourceManifest,
        item_ids: tuple[str, ...],
    ) -> SourceManifest:
        from meridian.lib.install.types import parse_item_id

        existing = manifest.find_source("meridian-base")
        required_agent_names = tuple(parse_item_id(item_id)[1] for item_id in item_ids)
        if existing is None:
            bootstrap_source = SourceConfig(
                name="meridian-base",
                kind="path",
                path=source_root.as_posix(),
                agents=required_agent_names,
            )
            # Use "shared" target for the bootstrap source (it's always shared)
            return manifest.with_source(bootstrap_source, target="shared")
        return manifest

    monkeypatch.setattr(
        "meridian.lib.install.bootstrap.ensure_bootstrap_source_manifest",
        fake_ensure_bootstrap_source_manifest,
    )

    plan = plan_bootstrap_assets(
        repo_root=repo_root,
        agent_names=("__meridian-subagent",),
    )
    ensure_bootstrap_assets(repo_root=repo_root, plan=plan)

    installed_path = repo_root / ".agents" / "agents" / "__meridian-subagent.md"
    assert installed_path.is_file()

    state_paths = resolve_state_paths(repo_root)
    config = load_sources_config(state_paths.agents_manifest_path)
    assert [source.name for source in config.sources] == ["meridian-base"]
    assert config.sources[0].kind == "path"
    assert config.sources[0].agents is not None
    assert "agent:__meridian-subagent" in [
        ref.item_id for ref in (config.sources[0].effective_items or ())
    ]

    lock = read_lock(state_paths.agents_lock_path)
    assert "meridian-base" in lock.sources
    assert "agent:__meridian-subagent" in lock.items


def test_ensure_bootstrap_assets_rehydrates_missing_bootstrap_manifest_from_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source_root = tmp_path / "bootstrap-source"
    _write_source_tree(source_root, agent_name="__meridian-subagent")

    paths = resolve_state_paths(repo_root)
    config = SourcesConfig(
        sources=(
            SourceConfig(
                name="meridian-base",
                kind="path",
                path=source_root.as_posix(),
                agents=("__meridian-subagent",),
            ),
        )
    )
    write_sources_config(paths.agents_manifest_path, config)

    lock = read_lock(paths.agents_lock_path)
    reconcile_sources(
        repo_root=repo_root,
        sources=config.sources,
        lock=lock,
        agents_cache_dir=paths.agents_cache_dir,
    )
    write_lock(paths.agents_lock_path, lock)

    installed_path = repo_root / ".agents" / "agents" / "__meridian-subagent.md"
    installed_path.unlink()
    paths.agents_manifest_path.unlink()

    def fake_ensure_bootstrap_source_manifest(
        *,
        manifest: SourceManifest,
        item_ids: tuple[str, ...],
    ) -> SourceManifest:
        from meridian.lib.install.types import parse_item_id

        required_agent_names = tuple(parse_item_id(item_id)[1] for item_id in item_ids)
        bootstrap_source = SourceConfig(
            name="meridian-base",
            kind="path",
            path=source_root.as_posix(),
            agents=required_agent_names,
        )
        return manifest.with_source(bootstrap_source, target="shared")

    monkeypatch.setattr(
        "meridian.lib.install.bootstrap.ensure_bootstrap_source_manifest",
        fake_ensure_bootstrap_source_manifest,
    )

    plan = plan_bootstrap_assets(
        repo_root=repo_root,
        agent_names=("__meridian-subagent",),
    )
    ensure_bootstrap_assets(repo_root=repo_root, plan=plan)

    assert installed_path.is_file()
    rehydrated = load_sources_config(paths.agents_manifest_path)
    assert [source.name for source in rehydrated.sources] == ["meridian-base"]


def test_ensure_bootstrap_source_manifest_upgrades_partial_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synthetic_config = SourceConfig(
        name="meridian-base",
        kind="git",
        url="https://github.com/haowjy/meridian-base.git",
        ref="main",
        agents=("__meridian-orchestrator", "__meridian-subagent"),
        skills=("__meridian-orchestrate", "__meridian-spawn-agent"),
    )
    monkeypatch.setattr(
        "meridian.lib.install.bootstrap.bootstrap_source_config",
        lambda: synthetic_config,
    )

    manifest = SourceManifest(
        shared=SourcesConfig(
            sources=(
                SourceConfig(
                    name="meridian-base",
                    kind="git",
                    url="https://github.com/haowjy/meridian-base.git",
                    ref="main",
                    agents=("__meridian-subagent",),
                    skills=("__meridian-orchestrate",),
                ),
            )
        )
    )

    updated = ensure_bootstrap_source_manifest(
        manifest=manifest,
        item_ids=("agent:__meridian-subagent",),
    )

    source = updated.find_source("meridian-base")
    assert source is not None
    assert source.agents == ("__meridian-orchestrator", "__meridian-subagent")
    assert source.skills == ("__meridian-orchestrate", "__meridian-spawn-agent")


def test_ensure_bootstrap_assets_rejects_unknown_missing_default(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    plan = plan_bootstrap_assets(repo_root=repo_root, agent_names=("custom-agent",))

    try:
        ensure_bootstrap_assets(repo_root=repo_root, plan=plan)
    except FileNotFoundError as exc:
        assert "custom-agent" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected missing custom runtime default to fail.")


def test_planned_bootstrap_agent_names_uses_default_when_request_is_blank() -> None:
    assert planned_bootstrap_agent_names(
        configured_default="__meridian-subagent",
        requested_agent="",
        builtin_default="__meridian-orchestrator",
    ) == ("__meridian-subagent",)


def test_planned_bootstrap_agent_names_bootstraps_explicit_builtin_agent() -> None:
    assert planned_bootstrap_agent_names(
        configured_default="__meridian-subagent",
        requested_agent="__meridian-orchestrator",
        builtin_default="__meridian-orchestrator",
    ) == ("__meridian-orchestrator",)


def test_planned_bootstrap_agent_names_skips_non_bootstrap_explicit_agent() -> None:
    assert (
        planned_bootstrap_agent_names(
            configured_default="__meridian-subagent",
            requested_agent="coder",
            builtin_default="__meridian-orchestrator",
        )
        == ()
    )


def test_planned_bootstrap_agent_names_uses_builtin_when_configured_default_is_unmanaged() -> None:
    assert planned_bootstrap_agent_names(
        configured_default="dev-orchestration",
        requested_agent="",
        builtin_default="__meridian-orchestrator",
    ) == ("__meridian-orchestrator",)
