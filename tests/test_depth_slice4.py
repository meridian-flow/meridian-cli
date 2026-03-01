"""Depth limiting checks for Slice 4 spawn safeguards."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from meridian.lib.ops._run_execute import _run_child_env
from meridian.lib.ops.run import RunCreateInput, run_create, run_create_sync
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

    result = run_create_sync(
        RunCreateInput(
            prompt="blocked",
            model="gpt-5.3-codex",
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.status == "failed"
    assert result.error == "max_depth_exceeded"
    assert result.current_depth == 3
    assert result.max_depth == 3
    assert result.run_id is None
    assert not (tmp_path / ".meridian" / ".spaces").exists()


@pytest.mark.asyncio
async def test_run_create_async_refuses_when_depth_limit_reached(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "4")
    monkeypatch.setenv("MERIDIAN_MAX_DEPTH", "4")

    result = await run_create(
        RunCreateInput(
            prompt="blocked-async",
            model="gpt-5.3-codex",
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.status == "failed"
    assert result.error == "max_depth_exceeded"
    assert result.current_depth == 4
    assert result.max_depth == 4
    assert result.run_id is None
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
        "run_spawn",
        {"prompt": "blocked-mcp", "model": "gpt-5.3-codex"},
    )
    payload = _payload_from_result(raw)
    assert payload["status"] == "failed"
    assert payload["error"] == "max_depth_exceeded"
    assert payload["current_depth"] == 3
    assert payload["max_depth"] == 3
    assert payload["run_id"] is None
    assert not (repo_root / ".meridian" / ".spaces").exists()


def test_run_child_env_increments_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "2")
    env = _run_child_env("s9")
    assert env["MERIDIAN_DEPTH"] == "3"
    assert env["MERIDIAN_SPACE_ID"] == "s9"


def test_cli_run_spawn_depth_limit_returns_structured_error(
    package_root: Path,
    cli_env: dict[str, str],
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".agents" / "skills").mkdir(parents=True, exist_ok=True)

    env = dict(cli_env)
    env["MERIDIAN_REPO_ROOT"] = repo_root.as_posix()
    env["MERIDIAN_DEPTH"] = "3"
    env["MERIDIAN_MAX_DEPTH"] = "3"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "meridian",
            "--json",
            "run",
            "spawn",
            "--prompt",
            "blocked-cli",
            "--model",
            "gpt-5.3-codex",
        ],
        cwd=package_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["error"] == "max_depth_exceeded"
    assert payload["current_depth"] == 3
    assert payload["max_depth"] == 3
    assert payload["run_id"] is None
    assert not (repo_root / ".meridian" / ".spaces").exists()
