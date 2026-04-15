from __future__ import annotations

from pathlib import Path

import pytest

from meridian.lib.core.types import SpawnId
from meridian.lib.streaming.control_socket import ControlSocketServer
from meridian.lib.streaming.types import InjectResult


class _FakeManager:
    def __init__(self, *, state_root: Path) -> None:
        self.state_root = state_root
        self.inject_calls: list[tuple[SpawnId, str, str]] = []
        self.interrupt_calls: list[tuple[SpawnId, str]] = []

    async def inject(
        self,
        spawn_id: SpawnId,
        message: str,
        *,
        source: str,
        on_result=None,
    ) -> InjectResult:
        self.inject_calls.append((spawn_id, message, source))
        result = InjectResult(success=True, inbound_seq=4)
        if on_result is not None:
            on_result(result)
        return result

    async def interrupt(
        self,
        spawn_id: SpawnId,
        *,
        source: str,
        on_result=None,
    ) -> InjectResult:
        self.interrupt_calls.append((spawn_id, source))
        result = InjectResult(success=True, inbound_seq=7)
        if on_result is not None:
            on_result(result)
        return result


@pytest.mark.asyncio
async def test_interrupt_request_routes_to_manager(tmp_path: Path) -> None:
    manager = _FakeManager(state_root=tmp_path / ".meridian")
    server = ControlSocketServer(SpawnId("p1"), tmp_path / "control.sock", manager)

    result = await server._handle_request(b'{"type":"interrupt"}\n', object())  # type: ignore[arg-type]

    assert result == {"ok": True, "inbound_seq": 7}
    assert manager.interrupt_calls == [(SpawnId("p1"), "control_socket")]
    assert manager.inject_calls == []


@pytest.mark.asyncio
async def test_user_message_request_requires_text(tmp_path: Path) -> None:
    manager = _FakeManager(state_root=tmp_path / ".meridian")
    server = ControlSocketServer(SpawnId("p1"), tmp_path / "control.sock", manager)

    result = await server._handle_request(b'{"type":"user_message"}\n', object())  # type: ignore[arg-type]

    assert result == {"ok": False, "error": "user_message requires text"}
    assert manager.interrupt_calls == []
    assert manager.inject_calls == []


@pytest.mark.asyncio
async def test_control_socket_rejects_unsupported_message_types(tmp_path: Path) -> None:
    manager = _FakeManager(state_root=tmp_path / ".meridian")
    server = ControlSocketServer(SpawnId("p1"), tmp_path / "control.sock", manager)

    result = await server._handle_request(b'{"type":"unknown"}\n', object())  # type: ignore[arg-type]

    assert result == {"ok": False, "error": "unsupported request type: unknown"}
    assert manager.interrupt_calls == []
    assert manager.inject_calls == []
