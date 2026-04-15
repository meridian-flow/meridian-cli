import signal
from typing import get_args, get_origin

import pytest

from meridian.lib.harness.connections.base import HarnessConnection
from meridian.lib.harness.connections.claude_ws import ClaudeConnection
from meridian.lib.harness.connections.codex_ws import CodexConnection
from meridian.lib.harness.connections.opencode_http import OpenCodeConnection
from meridian.lib.harness.launch_spec import (
    ClaudeLaunchSpec,
    CodexLaunchSpec,
    OpenCodeLaunchSpec,
)


def test_all_streaming_connections_bind_harness_connection_protocol() -> None:
    expected = (
        (ClaudeConnection, ClaudeLaunchSpec),
        (CodexConnection, CodexLaunchSpec),
        (OpenCodeConnection, OpenCodeLaunchSpec),
    )
    for connection_cls, expected_spec in expected:
        assert issubclass(connection_cls, HarnessConnection)
        matching_bases = [
            base
            for base in getattr(connection_cls, "__orig_bases__", ())
            if get_origin(base) is HarnessConnection
        ]
        assert matching_bases
        assert get_args(matching_bases[0]) == (expected_spec,)
        connection_cls()


@pytest.mark.asyncio
async def test_claude_connection_cancel_interrupt_are_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = ClaudeConnection()
    connection._state = "connected"
    signal_calls: list[signal.Signals] = []

    async def _fake_signal(sig: signal.Signals) -> None:
        signal_calls.append(sig)

    monkeypatch.setattr(connection, "_signal_process", _fake_signal)

    await connection.send_interrupt()
    await connection.send_interrupt()
    await connection.send_cancel()
    await connection.send_cancel()

    assert signal_calls == [signal.SIGINT, signal.SIGINT]
    assert connection.state == "stopping"


@pytest.mark.asyncio
async def test_codex_connection_cancel_interrupt_are_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = CodexConnection()
    connection._state = "connected"
    connection._thread_id = "thread-1"
    connection._current_turn_id = "turn-1"
    request_methods: list[str] = []
    close_calls = 0

    async def _fake_request(
        method: str,
        params: dict[str, object] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, object]:
        _ = params, timeout_seconds
        request_methods.append(method)
        return {}

    async def _fake_close_ws() -> None:
        nonlocal close_calls
        close_calls += 1

    monkeypatch.setattr(connection, "_request", _fake_request)
    monkeypatch.setattr(connection, "_close_ws", _fake_close_ws)

    await connection.send_interrupt()
    await connection.send_interrupt()
    await connection.send_cancel()
    await connection.send_cancel()

    assert request_methods == ["turn/interrupt"]
    assert close_calls == 1
    assert connection.state == "stopping"


@pytest.mark.asyncio
async def test_opencode_connection_cancel_interrupt_are_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = OpenCodeConnection()
    connection._state = "connected"
    connection._session_id = "session-1"
    action_calls = 0

    async def _fake_post_session_action(
        *,
        path_templates: tuple[str, ...],
        payload_variants: tuple[dict[str, object], ...],
        accepted_statuses: frozenset[int],
    ) -> None:
        _ = path_templates, payload_variants, accepted_statuses
        nonlocal action_calls
        action_calls += 1

    monkeypatch.setattr(connection, "_post_session_action", _fake_post_session_action)

    await connection.send_interrupt()
    await connection.send_interrupt()
    await connection.send_cancel()
    await connection.send_cancel()

    assert action_calls == 2
    assert connection.state == "stopping"
