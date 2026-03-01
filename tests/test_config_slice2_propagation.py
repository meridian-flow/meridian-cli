"""Slice 2 config propagation checks for run operations."""

from __future__ import annotations

from pathlib import Path

import meridian.lib.ops.run as run_ops
import pytest
from meridian.lib.ops.run import RunCreateInput
from meridian.lib.safety.permissions import PermissionConfig, PermissionTier
from meridian.lib.space.space_file import create_space


def _write_config(repo_root: Path, content: str) -> None:
    config_path = repo_root / ".meridian" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(content, encoding="utf-8")


def _clear_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in (
        "MERIDIAN_DEPTH",
        "MERIDIAN_MAX_DEPTH",
        "MERIDIAN_MAX_RETRIES",
        "MERIDIAN_KILL_GRACE_SECONDS",
        "MERIDIAN_DEFAULT_PERMISSION_TIER",
    ):
        monkeypatch.delenv(env_name, raising=False)


def test_custom_max_retries_flows_to_execute_with_finalization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_config_env(monkeypatch)
    _write_config(
        tmp_path,
        "[defaults]\nmax_retries = 7\n",
    )
    monkeypatch.setenv("MERIDIAN_SPACE_ID", create_space(tmp_path, name="cfg-prop").id)

    captured: dict[str, float | int] = {}

    async def fake_execute_with_finalization(*args: object, **kwargs: object) -> int:
        captured["max_retries"] = int(kwargs["max_retries"])
        return 0

    monkeypatch.setattr(run_ops, "execute_with_finalization", fake_execute_with_finalization)

    run_ops.run_create_sync(
        RunCreateInput(
            prompt="max retries propagation",
            model="gpt-5.3-codex",
            repo_root=tmp_path.as_posix(),
        )
    )

    assert captured["max_retries"] == 7


def test_custom_default_permission_tier_flows_through_build_permission_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_config_env(monkeypatch)
    _write_config(
        tmp_path,
        "[permissions]\ndefault_tier = 'workspace-write'\n",
    )
    monkeypatch.setenv("MERIDIAN_SPACE_ID", create_space(tmp_path, name="cfg-prop").id)

    captured: dict[str, object] = {}

    def fake_build_permission_config(
        tier: str | None,
        *,
        unsafe: bool,
        default_tier: str,
    ) -> PermissionConfig:
        captured["tier"] = tier
        captured["unsafe"] = unsafe
        captured["default_tier"] = default_tier
        return PermissionConfig(tier=PermissionTier.WORKSPACE_WRITE, unsafe=unsafe)

    async def fake_execute_with_finalization(*args: object, **kwargs: object) -> int:
        return 0

    monkeypatch.setattr(run_ops, "build_permission_config", fake_build_permission_config)
    monkeypatch.setattr(run_ops, "execute_with_finalization", fake_execute_with_finalization)

    run_ops.run_create_sync(
        RunCreateInput(
            prompt="permission propagation",
            model="gpt-5.3-codex",
            repo_root=tmp_path.as_posix(),
        )
    )

    # The built-in 'agent' profile has sandbox=workspace-write, which becomes the
    # inferred tier when no explicit --permission flag is passed.
    assert captured["tier"] == "workspace-write"
    assert captured["unsafe"] is False
    assert captured["default_tier"] == "workspace-write"


def test_custom_kill_grace_seconds_flows_to_execute_with_finalization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_config_env(monkeypatch)
    _write_config(
        tmp_path,
        "[timeouts]\nkill_grace_seconds = 4.5\n",
    )
    monkeypatch.setenv("MERIDIAN_SPACE_ID", create_space(tmp_path, name="cfg-prop").id)

    captured: dict[str, float | int] = {}

    async def fake_execute_with_finalization(*args: object, **kwargs: object) -> int:
        captured["kill_grace_seconds"] = float(kwargs["kill_grace_seconds"])
        return 0

    monkeypatch.setattr(run_ops, "execute_with_finalization", fake_execute_with_finalization)

    run_ops.run_create_sync(
        RunCreateInput(
            prompt="kill grace propagation",
            model="gpt-5.3-codex",
            repo_root=tmp_path.as_posix(),
        )
    )

    assert captured["kill_grace_seconds"] == 4.5


def test_run_spawn_rejects_danger_permission_tier_without_unsafe_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_config_env(monkeypatch)
    with pytest.raises(ValueError, match="requires explicit --unsafe"):
        run_ops.run_create_sync(
            RunCreateInput(
                prompt="opencode danger warning",
                model="opencode-gpt-5.3-codex",
                permission_tier="danger",
                repo_root=tmp_path.as_posix(),
                dry_run=True,
            )
        )
