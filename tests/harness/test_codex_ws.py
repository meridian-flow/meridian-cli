from __future__ import annotations

import json

import pytest

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

    async def run_reader(self) -> None:
        await self._read_messages_loop()

    async def next_event(self):  # type: ignore[override]
        return await self._event_queue.get()


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
