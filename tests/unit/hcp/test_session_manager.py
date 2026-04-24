from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.connections.base import ConnectionConfig
from meridian.lib.harness.launch_spec import CodexLaunchSpec
from meridian.lib.hcp.errors import HcpError, HcpErrorCategory
from meridian.lib.hcp.session_manager import HcpSessionManager
from meridian.lib.hcp.types import ChatState
from meridian.lib.safety.permissions import UnsafeNoOpPermissionResolver
from meridian.lib.state import session_store
from meridian.lib.state.paths import RuntimePaths, resolve_runtime_paths
from meridian.lib.streaming.types import InjectResult


class FakeSpawnManager:
    def __init__(self, runtime_root: Path, project_root: Path) -> None:
        self.runtime_root = runtime_root
        self.project_root = project_root
        self.started: list[tuple[ConnectionConfig, object, object]] = []
        self.injected: list[tuple[SpawnId, str, str]] = []
        self.stopped: list[SpawnId] = []
        self.inject_gate: asyncio.Event | None = None

    async def start_spawn(
        self,
        config: ConnectionConfig,
        spec: object,
        *,
        drain_policy: object | None = None,
    ) -> object:
        self.started.append((config, spec, drain_policy))
        return object()

    async def inject(
        self,
        spawn_id: SpawnId,
        message: str,
        source: str = "control_socket",
        on_result: object | None = None,
    ) -> InjectResult:
        _ = on_result
        self.injected.append((spawn_id, message, source))
        if self.inject_gate is not None:
            await self.inject_gate.wait()
        return InjectResult(success=True)

    async def stop_spawn(
        self,
        spawn_id: SpawnId,
        **kwargs: Any,
    ) -> object:
        _ = kwargs
        self.stopped.append(spawn_id)
        return object()


def _manager(tmp_path: Path) -> tuple[HcpSessionManager, FakeSpawnManager, Path]:
    runtime_root = resolve_runtime_paths(tmp_path).root_dir
    fake = FakeSpawnManager(runtime_root, tmp_path)
    return HcpSessionManager(fake, runtime_root, idle_timeout_secs=60.0), fake, runtime_root


def _config(tmp_path: Path, spawn_id: SpawnId | None = None) -> ConnectionConfig:
    return ConnectionConfig(
        spawn_id=spawn_id or SpawnId("p1"),
        harness_id=HarnessId.CODEX,
        prompt="hello",
        project_root=tmp_path,
        env_overrides={},
    )


def _spec() -> CodexLaunchSpec:
    return CodexLaunchSpec(
        prompt="hello",
        permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
    )


def _read_lifecycle(runtime_root: Path, c_id: str) -> list[dict[str, object]]:
    path = RuntimePaths.from_root_dir(runtime_root).chat_lifecycle_path(c_id)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.asyncio
async def test_restore_from_stores_loads_primary_sessions_as_idle(tmp_path: Path) -> None:
    manager, _fake, runtime_root = _manager(tmp_path)
    c_id = session_store.start_session(
        runtime_root,
        harness="codex",
        harness_session_id="s1",
        model="gpt-test",
        kind="primary",
    )

    await manager.restore_from_stores()

    assert manager.get_chat_state(c_id) == ChatState.IDLE
    events = _read_lifecycle(runtime_root, c_id)
    assert events[-1]["event"] == "state_change"
    assert events[-1]["data"] == {"source": "restore", "state": "idle"}
    session_store.stop_session(runtime_root, c_id)


@pytest.mark.asyncio
async def test_concurrent_prompt_rejected(tmp_path: Path) -> None:
    manager, fake, _runtime_root = _manager(tmp_path)
    c_id, _p_id = await manager.create_chat(
        "hello",
        model="gpt-test",
        harness="codex",
        config=_config(tmp_path),
        spec=_spec(),
    )
    fake.inject_gate = asyncio.Event()

    first_prompt = asyncio.create_task(manager.prompt(c_id, "one"))
    await asyncio.sleep(0)
    with pytest.raises(HcpError) as exc_info:
        await manager.prompt(c_id, "two")

    assert exc_info.value.category == HcpErrorCategory.CONCURRENT_PROMPT
    fake.inject_gate.set()
    await first_prompt
    await manager.close_chat(c_id)


@pytest.mark.asyncio
async def test_chat_state_transitions_create_cancel_close(tmp_path: Path) -> None:
    manager, fake, _runtime_root = _manager(tmp_path)
    c_id, p_id = await manager.create_chat(
        "hello",
        model="gpt-test",
        harness="codex",
        config=_config(tmp_path),
        spec=_spec(),
    )

    assert manager.get_chat_state(c_id) == ChatState.ACTIVE
    assert manager.get_active_p_id(c_id) == p_id
    await manager.cancel(c_id)

    assert manager.get_chat_state(c_id) == ChatState.IDLE
    assert manager.get_active_p_id(c_id) is None
    assert fake.stopped == [p_id]

    await manager.close_chat(c_id)
    assert manager.get_chat_state(c_id) == ChatState.CLOSED


@pytest.mark.asyncio
async def test_lifecycle_event_writing(tmp_path: Path) -> None:
    manager, _fake, runtime_root = _manager(tmp_path)

    await manager._write_lifecycle_event("c99", "timer_set", {"timeout_secs": 5})

    events = _read_lifecycle(runtime_root, "c99")
    assert events == [
        {
            "data": {"timeout_secs": 5},
            "event": "timer_set",
            "ts": events[0]["ts"],
        }
    ]
