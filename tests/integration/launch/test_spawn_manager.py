from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import cast

import pytest

from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.connections.base import (
    ConnectionCapabilities,
    ConnectionConfig,
    HarnessEvent,
)
from meridian.lib.harness.launch_spec import CodexLaunchSpec, ResolvedLaunchSpec
from meridian.lib.safety.permissions import UnsafeNoOpPermissionResolver
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.state.spawn_store import start_spawn
from meridian.lib.streaming import spawn_manager as spawn_manager_module
from meridian.lib.streaming.spawn_manager import SpawnManager
from meridian.lib.streaming.types import InjectResult


def _build_config(spawn_id: SpawnId, repo_root: Path) -> ConnectionConfig:
    return ConnectionConfig(
        spawn_id=spawn_id,
        harness_id=HarnessId.CODEX,
        prompt="hello",
        repo_root=repo_root,
        env_overrides={},
    )


def _build_spec() -> CodexLaunchSpec:
    return CodexLaunchSpec(
        prompt="hello",
        permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
    )


def _read_output_event_types(state_root: Path, spawn_id: SpawnId) -> list[str]:
    output_path = state_root / "spawns" / str(spawn_id) / "output.jsonl"
    if not output_path.exists():
        return []
    events: list[str] = []
    for line in output_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = cast("dict[str, object]", json.loads(line))
        event_type = payload.get("event_type")
        if isinstance(event_type, str):
            events.append(event_type)
    return events


@pytest.mark.asyncio
async def test_wait_for_completion_survives_cleanup_without_private_hooks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path
    state_root = resolve_state_paths(repo_root).root_dir
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()

    class FakeControlSocketServer:
        def __init__(self, spawn_id: SpawnId, socket_path: Path, manager: SpawnManager) -> None:
            _ = spawn_id, manager
            self.socket_path = socket_path

        async def start(self) -> None:
            self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        async def stop(self) -> None:
            return None

    class FakeConnection:
        def __init__(self) -> None:
            self._spawn_id = SpawnId("")
            self.state = "created"
            self.capabilities = ConnectionCapabilities(
                mid_turn_injection="queue",
                supports_steer=True,
                supports_interrupt=True,
                supports_cancel=True,
                runtime_model_switch=False,
                structured_reasoning=False,
            )

        @property
        def harness_id(self) -> HarnessId:
            return HarnessId.CODEX

        @property
        def spawn_id(self) -> SpawnId:
            return self._spawn_id

        async def start(self, config: ConnectionConfig, spec: ResolvedLaunchSpec) -> None:
            _ = spec
            self._spawn_id = config.spawn_id
            self.state = "connected"

        async def stop(self) -> None:
            cleanup_started.set()
            await release_cleanup.wait()
            self.state = "stopped"

        def health(self) -> bool:
            return True

        async def send_user_message(self, text: str) -> None:
            _ = text

        async def send_interrupt(self) -> None:
            return None

        async def send_cancel(self) -> None:
            return None

        async def events(self):  # type: ignore[no-untyped-def]
            yield HarnessEvent(
                event_type="item.completed",
                harness_id="codex",
                payload={
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "done"},
                },
            )

    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        lambda _harness_id: FakeConnection,
    )

    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        kind="streaming",
        prompt="hello",
        launch_mode="foreground",
        status="running",
    )
    manager = SpawnManager(state_root=state_root, repo_root=repo_root)
    await manager.start_spawn(_build_config(spawn_id, repo_root), _build_spec())

    try:
        await asyncio.wait_for(cleanup_started.wait(), timeout=1.0)
        completion = await asyncio.wait_for(manager.wait_for_completion(spawn_id), timeout=1.0)
        assert completion is not None
        assert completion.status == "failed"
        assert completion.exit_code == 1
        assert completion.error == "connection_closed_without_terminal_event"

        # Session cleanup removes live connection before cleanup fully drains.
        assert manager.get_connection(spawn_id) is None

        inject_result = await manager.inject(spawn_id, "late message")
        assert inject_result == InjectResult(
            success=False,
            error=f"Spawn {spawn_id} is not active",
        )
        assert "item.completed" in _read_output_event_types(state_root, spawn_id)
    finally:
        release_cleanup.set()
        await asyncio.sleep(0)
        await manager.stop_spawn(spawn_id)
