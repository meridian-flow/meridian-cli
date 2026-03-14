from pathlib import Path

import pytest

from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.sync.install_config import ManagedSourceConfig, ManagedSourcesConfig
from meridian.lib.sync.install_config import load_install_config, write_install_config
from meridian.lib.sync.install_engine import reconcile_managed_sources
from meridian.lib.sync.install_lock import read_install_lock, write_install_lock
from meridian.lib.sync.install_types import ItemRef
from meridian.lib.sync.runtime_ensure import (
    ensure_runtime_assets,
    plan_required_runtime_assets,
    planned_runtime_agent_names,
)


def _write_source_tree(source_root: Path, *, agent_name: str) -> None:
    (source_root / "agents").mkdir(parents=True, exist_ok=True)
    (source_root / "agents" / f"{agent_name}.md").write_text(
        f"---\nname: {agent_name}\ndescription: Test agent\nmodel: gpt-5.3-codex\n---\nBody\n",
        encoding="utf-8",
    )


def test_ensure_runtime_assets_reinstalls_from_locked_source(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source_root = tmp_path / "source"
    _write_source_tree(source_root, agent_name="__meridian-subagent")

    paths = resolve_state_paths(repo_root)
    config = ManagedSourcesConfig(
        sources=(
            ManagedSourceConfig(
                name="local",
                kind="path",
                path=source_root.as_posix(),
            ),
        )
    )
    write_install_config(paths.agents_manifest_path, config)

    lock = read_install_lock(paths.agents_lock_path)
    reconcile_managed_sources(
        repo_root=repo_root,
        sources=config.sources,
        lock=lock,
        agents_cache_dir=paths.agents_cache_dir,
    )
    write_install_lock(paths.agents_lock_path, lock)

    installed_path = repo_root / ".agents" / "agents" / "__meridian-subagent.md"
    installed_path.unlink()

    plan = plan_required_runtime_assets(
        repo_root=repo_root,
        agent_names=("__meridian-subagent",),
    )
    ensure_runtime_assets(repo_root=repo_root, plan=plan)

    assert installed_path.is_file()
    lock_after = read_install_lock(paths.agents_lock_path)
    assert "agent:__meridian-subagent" in lock_after.items
    assert load_install_config(paths.agents_manifest_path).sources[0].name == "local"


def test_ensure_runtime_assets_bootstraps_missing_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source_root = tmp_path / "bootstrap-source"
    _write_source_tree(source_root, agent_name="__meridian-subagent")

    def fake_bootstrap_source(
        name: str,
        *,
        items: tuple[ItemRef, ...] | None = None,
    ) -> ManagedSourceConfig:
        assert name == "meridian-agents"
        return ManagedSourceConfig(
            name="meridian-agents",
            kind="path",
            path=source_root.as_posix(),
            items=items,
        )

    monkeypatch.setattr(
        "meridian.lib.sync.runtime_ensure.well_known_source_config",
        fake_bootstrap_source,
    )

    plan = plan_required_runtime_assets(
        repo_root=repo_root,
        agent_names=("__meridian-subagent",),
    )
    ensure_runtime_assets(repo_root=repo_root, plan=plan)

    installed_path = repo_root / ".agents" / "agents" / "__meridian-subagent.md"
    assert installed_path.is_file()

    state_paths = resolve_state_paths(repo_root)
    config = load_install_config(state_paths.agents_manifest_path)
    assert [source.name for source in config.sources] == ["meridian-agents"]
    assert config.sources[0].kind == "path"
    assert config.sources[0].items is not None
    assert config.sources[0].items[0].item_id == "agent:__meridian-subagent"

    lock = read_install_lock(state_paths.agents_lock_path)
    assert "meridian-agents" in lock.sources
    assert "agent:__meridian-subagent" in lock.items


def test_ensure_runtime_assets_rejects_unknown_missing_default(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    plan = plan_required_runtime_assets(repo_root=repo_root, agent_names=("custom-agent",))

    try:
        ensure_runtime_assets(repo_root=repo_root, plan=plan)
    except FileNotFoundError as exc:
        assert "custom-agent" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected missing custom runtime default to fail.")


def test_planned_runtime_agent_names_uses_default_when_request_is_blank() -> None:
    assert planned_runtime_agent_names(
        configured_default="__meridian-subagent",
        requested_agent="",
    ) == ("__meridian-subagent",)


def test_planned_runtime_agent_names_bootstraps_explicit_builtin_agent() -> None:
    assert planned_runtime_agent_names(
        configured_default="__meridian-subagent",
        requested_agent="__meridian-orchestrator",
    ) == ("__meridian-orchestrator",)


def test_planned_runtime_agent_names_skips_non_bootstrap_explicit_agent() -> None:
    assert (
        planned_runtime_agent_names(
            configured_default="__meridian-subagent",
            requested_agent="coder",
        )
        == ()
    )
