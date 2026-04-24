from __future__ import annotations

from pathlib import Path

import pytest

from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.connections.base import ConnectionConfig
from meridian.lib.harness.launch_spec import CodexLaunchSpec, OpenCodeLaunchSpec
from meridian.lib.hcp.adapters import get_hcp_adapter
from meridian.lib.hcp.adapters.claude import ClaudeHcpAdapter
from meridian.lib.hcp.adapters.codex import CodexHcpAdapter
from meridian.lib.hcp.adapters.opencode import OpenCodeHcpAdapter
from meridian.lib.hcp.capabilities import (
    CLAUDE_CAPABILITIES,
    CODEX_CAPABILITIES,
    OPENCODE_CAPABILITIES,
)
from meridian.lib.safety.permissions import UnsafeNoOpPermissionResolver


def _config(tmp_path: Path, harness_id: HarnessId) -> ConnectionConfig:
    return ConnectionConfig(
        spawn_id=SpawnId("p1"),
        harness_id=harness_id,
        prompt="hello",
        project_root=tmp_path,
        env_overrides={},
    )


def _codex_spec() -> CodexLaunchSpec:
    return CodexLaunchSpec(
        prompt="hello",
        permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
    )


def _opencode_spec() -> OpenCodeLaunchSpec:
    return OpenCodeLaunchSpec(
        prompt="hello",
        permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
    )


def test_capability_declarations() -> None:
    assert ClaudeHcpAdapter().capabilities == CLAUDE_CAPABILITIES
    assert CodexHcpAdapter().capabilities == CODEX_CAPABILITIES
    assert OpenCodeHcpAdapter().capabilities == OPENCODE_CAPABILITIES


def test_adapter_registration_returns_expected_types() -> None:
    assert isinstance(get_hcp_adapter(HarnessId.CLAUDE), ClaudeHcpAdapter)
    assert isinstance(get_hcp_adapter(HarnessId.CODEX), CodexHcpAdapter)
    assert isinstance(get_hcp_adapter(HarnessId.OPENCODE), OpenCodeHcpAdapter)


@pytest.mark.asyncio
async def test_claude_create_session_returns_empty_id(tmp_path: Path) -> None:
    adapter = ClaudeHcpAdapter()

    session_id = await adapter.create_session(
        _config(tmp_path, HarnessId.CLAUDE),
        _codex_spec(),
    )

    assert session_id == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter", "harness_id", "spec"),
    (
        (CodexHcpAdapter(), HarnessId.CODEX, _codex_spec()),
        (OpenCodeHcpAdapter(), HarnessId.OPENCODE, _opencode_spec()),
    ),
)
async def test_create_session_returns_empty_id_for_async_extraction(
    tmp_path: Path,
    adapter: CodexHcpAdapter | OpenCodeHcpAdapter,
    harness_id: HarnessId,
    spec: object,
) -> None:
    session_id = await adapter.create_session(_config(tmp_path, harness_id), spec)  # pyright: ignore[reportArgumentType]

    assert session_id == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter", "harness_id", "spec"),
    (
        (CodexHcpAdapter(), HarnessId.CODEX, _codex_spec()),
        (OpenCodeHcpAdapter(), HarnessId.OPENCODE, _opencode_spec()),
    ),
)
async def test_resume_returns_existing_harness_session_id(
    tmp_path: Path,
    adapter: CodexHcpAdapter | OpenCodeHcpAdapter,
    harness_id: HarnessId,
    spec: CodexLaunchSpec | OpenCodeLaunchSpec,
) -> None:
    session_id = await adapter.resume_session(
        "parent-session",
        _config(tmp_path, harness_id),
        spec,
    )

    assert session_id == "parent-session"


@pytest.mark.asyncio
async def test_claude_resume_returns_harness_session_id(tmp_path: Path) -> None:
    adapter = ClaudeHcpAdapter()

    session_id = await adapter.resume_session(
        "claude-session",
        _config(tmp_path, HarnessId.CLAUDE),
        _codex_spec(),
    )

    assert session_id == "claude-session"
