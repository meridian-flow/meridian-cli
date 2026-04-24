from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import pytest

from meridian.lib.platform import IS_WINDOWS
from meridian.lib.state import spawn_store

spawn_inject = importlib.import_module("meridian.cli.spawn_inject")


class _FakeReader:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def readline(self) -> bytes:
        return self._payload


class _FakeWriter:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


def _create_running_spawn_layout(runtime_root: Path, spawn_id: str) -> None:
    spawn_store.start_spawn(
        runtime_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
        spawn_id=spawn_id,
    )
    spawn_dir = runtime_root / "spawns" / spawn_id
    spawn_dir.mkdir(parents=True, exist_ok=True)
    if IS_WINDOWS:
        (spawn_dir / "control.port").write_text("12345", encoding="utf-8")
    else:
        (spawn_dir / "control.sock").write_text("", encoding="utf-8")


def _create_running_spawn_layout_for_validation_path(runtime_root: Path, spawn_id: str) -> None:
    """Create spawn layout WITHOUT control endpoint.

    This tests that validation runs BEFORE endpoint discovery.
    If validation comes first, we get "message is required".
    If discovery comes first, we get "no control endpoint".
    """
    spawn_store.start_spawn(
        runtime_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
        spawn_id=spawn_id,
    )
    spawn_dir = runtime_root / "spawns" / spawn_id
    spawn_dir.mkdir(parents=True, exist_ok=True)
    # Intentionally DO NOT create control.sock or control.port.
    # This proves validation runs before discovery.


def test_inject_requires_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime_root = tmp_path / ".meridian"
    runtime_root.mkdir(parents=True, exist_ok=True)
    _create_running_spawn_layout_for_validation_path(runtime_root, "p1")

    monkeypatch.setattr(spawn_inject, "resolve_runtime_root_and_config", lambda _: (tmp_path, None))
    monkeypatch.setattr(spawn_inject, "resolve_runtime_root", lambda _project_root: runtime_root)

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(spawn_inject.inject_message("p1", ""))

    assert exc_info.value.code == 1
    assert "message is required" in capsys.readouterr().err


def test_message_inject_allows_self_caller_and_sends_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime_root = tmp_path / ".meridian"
    runtime_root.mkdir(parents=True, exist_ok=True)
    _create_running_spawn_layout(runtime_root, "p1")

    monkeypatch.setattr(spawn_inject, "resolve_runtime_root_and_config", lambda _: (tmp_path, None))
    monkeypatch.setattr(spawn_inject, "resolve_runtime_root", lambda _project_root: runtime_root)

    writer = _FakeWriter()

    if IS_WINDOWS:

        async def _fake_tcp_connect(host: str, port: int) -> tuple[_FakeReader, _FakeWriter]:
            return _FakeReader(b'{"ok":true}\n'), writer

        monkeypatch.setattr(asyncio, "open_connection", _fake_tcp_connect)
    else:

        async def _fake_unix_connect(path: str) -> tuple[_FakeReader, _FakeWriter]:
            assert path.endswith("/spawns/p1/control.sock")
            return _FakeReader(b'{"ok":true}\n'), writer

        monkeypatch.setattr(asyncio, "open_unix_connection", _fake_unix_connect)

    asyncio.run(spawn_inject.inject_message("p1", "hello"))

    assert writer.writes == [b'{"type":"user_message","text":"hello"}\n']
    assert "Message delivered to spawn p1" in capsys.readouterr().out
