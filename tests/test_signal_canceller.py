from __future__ import annotations

import asyncio
import json
import os
import signal
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

import pytest

from meridian.lib.core.types import SpawnId
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.state.spawn_store import LaunchMode
from meridian.lib.streaming.signal_canceller import SignalCanceller


def _start_spawn(
    state_root: Path,
    *,
    spawn_id: str,
    launch_mode: LaunchMode,
    runner_pid: int | None = None,
) -> str:
    return str(
        spawn_store.start_spawn(
            state_root,
            chat_id="c1",
            model="gpt-5.4",
            agent="coder",
            harness="codex",
            prompt="hello",
            spawn_id=spawn_id,
            launch_mode=launch_mode,
            runner_pid=runner_pid,
        )
    )


@pytest.mark.asyncio
async def test_signal_canceller_returns_idempotent_outcome_for_terminal_spawn(
    tmp_path: Path,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    spawn_id = _start_spawn(state_root, spawn_id="p1", launch_mode="foreground")
    spawn_store.finalize_spawn(
        state_root,
        spawn_id,
        status="failed",
        exit_code=1,
        origin="runner",
        error="boom",
    )

    outcome = await SignalCanceller(state_root=state_root).cancel(SpawnId(spawn_id))

    assert outcome.already_terminal is True
    assert outcome.status == "failed"
    assert outcome.origin == "runner"
    assert outcome.exit_code == 1


@pytest.mark.asyncio
async def test_signal_canceller_finalizing_gate_skips_sigterm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    spawn_id = _start_spawn(state_root, spawn_id="p1", launch_mode="foreground", runner_pid=4321)
    assert spawn_store.mark_finalizing(state_root, spawn_id) is True

    def _unexpected_kill(pid: int, sig: int) -> None:
        raise AssertionError(f"os.kill must not run for finalizing rows: pid={pid}, sig={sig}")

    monkeypatch.setattr(os, "kill", _unexpected_kill)
    outcome = await SignalCanceller(state_root=state_root, grace_seconds=0.01).cancel(
        SpawnId(spawn_id)
    )

    assert outcome.status == "finalizing"
    assert outcome.finalizing is True


@pytest.mark.asyncio
async def test_signal_canceller_cli_lane_sends_sigterm_and_returns_terminal_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    spawn_id = _start_spawn(state_root, spawn_id="p1", launch_mode="foreground", runner_pid=7654)

    monkeypatch.setattr(
        "meridian.lib.streaming.signal_canceller.is_process_alive",
        lambda pid, created_after_epoch=None: pid == 7654,
    )
    sent_signals: list[tuple[int, int]] = []

    def _fake_kill(pid: int, sig: int) -> None:
        sent_signals.append((pid, sig))
        spawn_store.finalize_spawn(
            state_root,
            spawn_id,
            status="cancelled",
            exit_code=143,
            origin="runner",
            error="cancelled",
        )

    monkeypatch.setattr(os, "kill", _fake_kill)
    outcome = await SignalCanceller(state_root=state_root).cancel(SpawnId(spawn_id))

    assert sent_signals == [(7654, signal.SIGTERM)]
    assert outcome.status == "cancelled"
    assert outcome.origin == "runner"
    assert outcome.exit_code == 143
    assert outcome.finalizing is False


@pytest.mark.asyncio
async def test_signal_canceller_app_lane_uses_manager_stop_spawn(
    tmp_path: Path,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    spawn_id = _start_spawn(state_root, spawn_id="p1", launch_mode="app", runner_pid=3456)
    calls: list[tuple[str, str, int, str | None]] = []

    class _FakeManager:
        async def stop_spawn(
            self,
            target_spawn_id: SpawnId,
            *,
            status: str = "cancelled",
            exit_code: int = 1,
            error: str | None = None,
        ) -> None:
            calls.append((str(target_spawn_id), status, exit_code, error))
            spawn_store.finalize_spawn(
                state_root,
                target_spawn_id,
                status="cancelled",
                exit_code=143,
                origin="runner",
                error="cancelled",
            )

    outcome = await SignalCanceller(
        state_root=state_root,
        manager=cast("Any", _FakeManager()),
    ).cancel(SpawnId(spawn_id))

    assert calls == [(spawn_id, "cancelled", 143, "cancelled")]
    assert outcome.status == "cancelled"
    assert outcome.origin == "runner"


@pytest.mark.asyncio
async def test_signal_canceller_cli_lane_finalizes_when_runner_pid_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    spawn_id = _start_spawn(state_root, spawn_id="p1", launch_mode="foreground", runner_pid=None)

    monkeypatch.setattr(
        "meridian.lib.streaming.signal_canceller.is_process_alive",
        lambda pid, created_after_epoch=None: False,
    )
    outcome = await SignalCanceller(state_root=state_root).cancel(SpawnId(spawn_id))

    assert outcome.status == "cancelled"
    assert outcome.origin == "cancel"
    assert outcome.exit_code == 130


async def _start_http_socket_server(
    socket_path: Path,
    *,
    status_code: int,
    body: dict[str, object],
    on_request: Callable[[], None] | None = None,
) -> asyncio.AbstractServer:
    socket_path.unlink(missing_ok=True)

    async def _handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        with suppress(Exception):
            while True:
                line = await reader.readline()
                if not line or line == b"\r\n":
                    break
        if on_request is not None:
            on_request()
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        status_text = {
            200: "OK",
            404: "Not Found",
            409: "Conflict",
            503: "Service Unavailable",
        }.get(status_code, "Error")
        writer.write(
            (
                f"HTTP/1.1 {status_code} {status_text}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode()
            + payload
        )
        with suppress(Exception):
            await writer.drain()
        writer.close()
        with suppress(Exception):
            await writer.wait_closed()

    return await asyncio.start_unix_server(_handler, path=str(socket_path))


@pytest.mark.asyncio
async def test_signal_canceller_app_lane_cross_process_http_success(
    tmp_path: Path,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    spawn_id = _start_spawn(state_root, spawn_id="p1", launch_mode="app")
    socket_path = state_root / "app.sock"

    def _finalize_spawn() -> None:
        spawn_store.finalize_spawn(
            state_root,
            spawn_id,
            status="cancelled",
            exit_code=143,
            origin="runner",
            error="cancelled",
        )

    server = await _start_http_socket_server(
        socket_path,
        status_code=200,
        body={"ok": True, "status": "cancelled", "origin": "runner"},
        on_request=_finalize_spawn,
    )
    try:
        outcome = await SignalCanceller(state_root=state_root).cancel(SpawnId(spawn_id))
    finally:
        server.close()
        await server.wait_closed()

    assert outcome.status == "cancelled"
    assert outcome.origin == "runner"
    assert outcome.exit_code == 143
    assert outcome.finalizing is False


@pytest.mark.asyncio
async def test_signal_canceller_app_lane_cross_process_http_409_maps_already_terminal(
    tmp_path: Path,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    spawn_id = _start_spawn(state_root, spawn_id="p1", launch_mode="app")
    socket_path = state_root / "app.sock"

    server = await _start_http_socket_server(
        socket_path,
        status_code=409,
        body={"detail": "spawn already terminal: failed"},
    )
    try:
        outcome = await SignalCanceller(state_root=state_root).cancel(SpawnId(spawn_id))
    finally:
        server.close()
        await server.wait_closed()

    assert outcome.already_terminal is True
    assert outcome.status == "failed"
    assert outcome.origin == "cancel"
    assert outcome.finalizing is False


@pytest.mark.asyncio
async def test_signal_canceller_app_lane_cross_process_http_503_maps_finalizing(
    tmp_path: Path,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    spawn_id = _start_spawn(state_root, spawn_id="p1", launch_mode="app")
    socket_path = state_root / "app.sock"

    server = await _start_http_socket_server(
        socket_path,
        status_code=503,
        body={"detail": "spawn is finalizing"},
    )
    try:
        outcome = await SignalCanceller(state_root=state_root).cancel(SpawnId(spawn_id))
    finally:
        server.close()
        await server.wait_closed()

    assert outcome.finalizing is True
    assert outcome.status == "finalizing"
    assert outcome.origin == "cancel"
