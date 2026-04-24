from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

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


class FakeConnection:
    started: ClassVar[list[tuple[ConnectionConfig, object]]] = []
    next_session_id: ClassVar[str] = "session-created"

    def __init__(self) -> None:
        self._session_id: str | None = None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    async def start(self, config: ConnectionConfig, spec: object) -> None:
        self.started.append((config, spec))
        self._session_id = self.next_session_id


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
    ("adapter", "harness_id", "spec", "module_name"),
    (
        (CodexHcpAdapter(), HarnessId.CODEX, _codex_spec(), "meridian.lib.hcp.adapters.codex"),
        (
            OpenCodeHcpAdapter(),
            HarnessId.OPENCODE,
            _opencode_spec(),
            "meridian.lib.hcp.adapters.opencode",
        ),
    ),
)
async def test_create_session_returns_connection_session_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    adapter: CodexHcpAdapter | OpenCodeHcpAdapter,
    harness_id: HarnessId,
    spec: object,
    module_name: str,
) -> None:
    FakeConnection.started = []
    monkeypatch.setattr(f"{module_name}.get_connection_class", lambda _harness_id: FakeConnection)

    session_id = await adapter.create_session(_config(tmp_path, harness_id), spec)  # pyright: ignore[reportArgumentType]

    assert session_id == "session-created"
    assert FakeConnection.started[0][1] is spec


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter", "harness_id", "spec", "module_name"),
    (
        (CodexHcpAdapter(), HarnessId.CODEX, _codex_spec(), "meridian.lib.hcp.adapters.codex"),
        (
            OpenCodeHcpAdapter(),
            HarnessId.OPENCODE,
            _opencode_spec(),
            "meridian.lib.hcp.adapters.opencode",
        ),
    ),
)
async def test_resume_populates_continue_session_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    adapter: CodexHcpAdapter | OpenCodeHcpAdapter,
    harness_id: HarnessId,
    spec: Any,
    module_name: str,
) -> None:
    FakeConnection.started = []
    FakeConnection.next_session_id = "session-resumed"
    monkeypatch.setattr(f"{module_name}.get_connection_class", lambda _harness_id: FakeConnection)

    session_id = await adapter.resume_session(
        "parent-session",
        _config(tmp_path, harness_id),
        spec,
    )

    assert session_id == "session-resumed"
    started_spec = FakeConnection.started[0][1]
    assert started_spec is not spec
    assert started_spec.continue_session_id == "parent-session"


@pytest.mark.asyncio
async def test_claude_resume_returns_harness_session_id(tmp_path: Path) -> None:
    adapter = ClaudeHcpAdapter()

    session_id = await adapter.resume_session(
        "claude-session",
        _config(tmp_path, HarnessId.CLAUDE),
        _codex_spec(),
    )

    assert session_id == "claude-session"
