from __future__ import annotations

import json
from pathlib import Path

import pytest

from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.connections.base import ConnectionConfig
from meridian.lib.harness.connections.codex_ws import CodexConnection


class _FakeWebSocket:
    def __init__(self, messages: list[str]) -> None:
        self._messages = iter(messages)
        self.sent: list[str] = []
        self.closed = False

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True

    def __aiter__(self) -> _FakeWebSocket:
        return self

    async def __anext__(self) -> str:
        try:
            return next(self._messages)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _TestableCodexConnection(CodexConnection):
    def attach_websocket(self, ws: _FakeWebSocket) -> None:
        self._state = "connected"
        self._ws = ws

    def thread_bootstrap_request_for_test(
        self,
        config: ConnectionConfig,
        params: SpawnParams,
    ) -> tuple[str, dict[str, object]]:
        return self._thread_bootstrap_request(config, params)

    async def run_reader(self) -> None:
        await self._read_messages_loop()

    async def next_event(self):  # type: ignore[override]
        return await self._event_queue.get()


def _build_config(tmp_path: Path) -> ConnectionConfig:
    return ConnectionConfig(
        spawn_id=SpawnId("p321"),
        harness_id=HarnessId.CODEX,
        model="gpt-5.4",
        prompt="hello",
        repo_root=tmp_path,
        env_overrides={},
    )


@pytest.mark.asyncio
async def test_codex_ws_auto_accepts_command_execution_approval_requests() -> None:
    message = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "itemId": "call-1",
            },
        }
    )
    ws = _FakeWebSocket([message])
    connection = _TestableCodexConnection()
    connection.attach_websocket(ws)

    await connection.run_reader()

    assert [json.loads(payload) for payload in ws.sent] == [
        {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {"decision": "accept"},
        }
    ]
    assert await connection.next_event() is None


@pytest.mark.asyncio
async def test_codex_ws_rejects_unsupported_server_requests_explicitly() -> None:
    message = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "item/tool/call",
            "params": {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "callId": "tool-1",
                "tool": "lookup_ticket",
                "arguments": {"id": "ABC-123"},
            },
        }
    )
    ws = _FakeWebSocket([message])
    connection = _TestableCodexConnection()
    connection.attach_websocket(ws)

    await connection.run_reader()

    warning_event = await connection.next_event()
    assert warning_event is not None
    assert warning_event.event_type == "warning/unsupportedServerRequest"
    assert warning_event.payload["method"] == "item/tool/call"
    assert [json.loads(payload) for payload in ws.sent] == [
        {
            "jsonrpc": "2.0",
            "id": 9,
            "error": {
                "code": -32601,
                "message": (
                    "Meridian codex_ws adapter does not support server request "
                    "'item/tool/call'"
                ),
            },
        }
    ]
    assert await connection.next_event() is None


def test_codex_ws_thread_bootstrap_request_starts_new_thread(tmp_path: Path) -> None:
    connection = _TestableCodexConnection()

    method, payload = connection.thread_bootstrap_request_for_test(
        _build_config(tmp_path),
        SpawnParams(prompt="hello"),
    )

    assert method == "thread/start"
    assert payload == {"cwd": str(tmp_path), "model": "gpt-5.4"}


def test_codex_ws_thread_bootstrap_request_resumes_existing_thread(tmp_path: Path) -> None:
    connection = _TestableCodexConnection()

    method, payload = connection.thread_bootstrap_request_for_test(
        _build_config(tmp_path),
        SpawnParams(prompt="hello", continue_harness_session_id="thread-123"),
    )

    assert method == "thread/resume"
    assert payload == {
        "cwd": str(tmp_path),
        "model": "gpt-5.4",
        "threadId": "thread-123",
    }


def test_codex_ws_thread_bootstrap_request_forks_existing_thread(tmp_path: Path) -> None:
    connection = _TestableCodexConnection()

    method, payload = connection.thread_bootstrap_request_for_test(
        _build_config(tmp_path),
        SpawnParams(
            prompt="hello",
            continue_harness_session_id="thread-123",
            continue_fork=True,
        ),
    )

    assert method == "thread/fork"
    assert payload == {
        "cwd": str(tmp_path),
        "model": "gpt-5.4",
        "threadId": "thread-123",
    }
