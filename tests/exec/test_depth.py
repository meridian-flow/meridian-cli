"""Depth limit and child environment invariants for spawn creation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from meridian.lib.ops._spawn_execute import _spawn_child_env
from meridian.lib.ops.spawn import SpawnCreateInput, spawn_create, spawn_create_sync
from meridian.server.main import mcp


def _payload_from_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    for block in result:
        text = getattr(block, "text", None)
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise AssertionError("Tool result did not include a JSON object payload")


def test_run_create_sync_refuses_when_depth_limit_reached(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "3")
    monkeypatch.setenv("MERIDIAN_MAX_DEPTH", "3")

    result = spawn_create_sync(
        SpawnCreateInput(
            prompt="blocked",
            model="gpt-5.3-codex",
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.status == "failed"
    assert result.error == "max_depth_exceeded"
    assert result.current_depth == 3
    assert result.max_depth == 3
    assert result.spawn_id is None
    assert not (tmp_path / ".meridian" / ".spaces").exists()


@pytest.mark.asyncio
async def test_run_create_async_refuses_when_depth_limit_reached(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "4")
    monkeypatch.setenv("MERIDIAN_MAX_DEPTH", "4")

    result = await spawn_create(
        SpawnCreateInput(
            prompt="blocked-async",
            model="gpt-5.3-codex",
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.status == "failed"
    assert result.error == "max_depth_exceeded"
    assert result.current_depth == 4
    assert result.max_depth == 4
    assert result.spawn_id is None
    assert not (tmp_path / ".meridian" / ".spaces").exists()


@pytest.mark.asyncio
async def test_mcp_run_spawn_refuses_when_depth_limit_reached(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".agents" / "skills").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MERIDIAN_REPO_ROOT", repo_root.as_posix())
    monkeypatch.setenv("MERIDIAN_DEPTH", "3")
    monkeypatch.setenv("MERIDIAN_MAX_DEPTH", "3")

    raw = await mcp.call_tool(
        "spawn_create",
        {"prompt": "blocked-mcp", "model": "gpt-5.3-codex"},
    )
    payload = _payload_from_result(raw)
    assert payload["status"] == "failed"
    assert payload["error"] == "max_depth_exceeded"
    assert "spawn_id" not in payload
    assert not (repo_root / ".meridian" / ".spaces").exists()


def test_run_child_env_increments_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "2")
    env = _spawn_child_env("s9")
    assert env["MERIDIAN_DEPTH"] == "3"
    assert env["MERIDIAN_SPACE_ID"] == "s9"
