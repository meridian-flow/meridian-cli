from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import pytest

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


def _create_running_spawn_layout(state_root: Path, spawn_id: str) -> None:
    spawn_store.start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
        spawn_id=spawn_id,
    )
    spawn_dir = state_root / "spawns" / spawn_id
    spawn_dir.mkdir(parents=True, exist_ok=True)
    (spawn_dir / "control.sock").write_text("", encoding="utf-8")


def test_inject_requires_message_or_interrupt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state_root = tmp_path / ".meridian"
    state_root.mkdir(parents=True, exist_ok=True)
    _create_running_spawn_layout(state_root, "p1")

    monkeypatch.setattr(spawn_inject, "resolve_runtime_root_and_config", lambda _: (tmp_path, None))
    monkeypatch.setattr(spawn_inject, "resolve_state_root", lambda _repo_root: state_root)

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(spawn_inject.inject_message("p1", None, interrupt=False))

    assert exc_info.value.code == 1
    assert "provide a message or --interrupt" in capsys.readouterr().err


def test_interrupt_inject_allows_self_caller_and_sends_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state_root = tmp_path / ".meridian"
    state_root.mkdir(parents=True, exist_ok=True)
    _create_running_spawn_layout(state_root, "p1")

    monkeypatch.setattr(spawn_inject, "resolve_runtime_root_and_config", lambda _: (tmp_path, None))
    monkeypatch.setattr(spawn_inject, "resolve_state_root", lambda _repo_root: state_root)

    writer = _FakeWriter()

    async def _fake_open(path: str) -> tuple[_FakeReader, _FakeWriter]:
        assert path.endswith("/spawns/p1/control.sock")
        return _FakeReader(b'{"ok":true}\n'), writer

    monkeypatch.setattr(asyncio, "open_unix_connection", _fake_open)

    asyncio.run(spawn_inject.inject_message("p1", None, interrupt=True))

    assert writer.writes == [b'{"type":"interrupt"}\n']
    assert "Interrupt delivered to spawn p1" in capsys.readouterr().out
