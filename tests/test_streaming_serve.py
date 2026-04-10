from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import cast

import pytest

from meridian.cli import streaming_serve as streaming_serve_module
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.state.spawn_store import get_spawn


def _read_spawn_events(state_root: Path) -> list[dict[str, object]]:
    events_path = state_root / "spawns.jsonl"
    return [
        cast("dict[str, object]", json.loads(line))
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.mark.asyncio
async def test_streaming_serve_shutdown_finalizes_once_as_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path
    state_root = resolve_state_paths(repo_root).root_dir
    shutdown_calls: list[tuple[str, int, str | None]] = []

    class FakeManager:
        def __init__(self, *, state_root: Path, repo_root: Path) -> None:
            self._state_root = state_root
            self._repo_root = repo_root

        async def start_spawn(self, config: object) -> None:
            _ = config

        def subscribe(self, spawn_id: str) -> asyncio.Queue[object | None]:
            _ = spawn_id
            return asyncio.Queue()

        def unsubscribe(self, spawn_id: str) -> None:
            _ = spawn_id

        async def shutdown(
            self,
            *,
            status: str = "cancelled",
            exit_code: int = 1,
            error: str | None = None,
        ) -> None:
            shutdown_calls.append((status, exit_code, error))
            from meridian.lib.state import spawn_store

            spawn_store.finalize_spawn(
                self._state_root,
                "p1",
                status=cast("object", status),
                exit_code=exit_code,
                error=error,
                duration_secs=1.0,
            )

    async def _wait_for_shutdown(shutdown_event: asyncio.Event) -> str:
        _ = shutdown_event
        return "shutdown_requested"

    async def _wait_forever(queue: asyncio.Queue[object | None]) -> str:
        _ = queue
        await asyncio.sleep(3600)
        return "connection_closed"

    monkeypatch.setattr(streaming_serve_module, "SpawnManager", FakeManager)
    monkeypatch.setattr(
        streaming_serve_module,
        "resolve_runtime_root_and_config",
        lambda repo_root=None, *, sink=None: (repo_root or tmp_path, None),
    )
    monkeypatch.setattr(streaming_serve_module, "_install_signal_handlers", lambda *_: [])
    monkeypatch.setattr(streaming_serve_module, "_remove_signal_handlers", lambda *_: None)
    monkeypatch.setattr(streaming_serve_module, "_wait_for_shutdown", _wait_for_shutdown)
    monkeypatch.setattr(streaming_serve_module, "_wait_for_connection_close", _wait_forever)

    await streaming_serve_module.streaming_serve("codex", "hello")

    assert shutdown_calls == [("cancelled", 1, None)]
    events = _read_spawn_events(state_root)
    assert [event["event"] for event in events] == ["start", "finalize"]
    assert events[-1]["status"] == "cancelled"

    row = get_spawn(state_root, "p1")
    assert row is not None
    assert row.status == "cancelled"
    assert row.exit_code == 1


@pytest.mark.asyncio
async def test_streaming_serve_start_failure_finalizes_failed_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path
    state_root = resolve_state_paths(repo_root).root_dir

    class FakeManager:
        def __init__(self, *, state_root: Path, repo_root: Path) -> None:
            _ = state_root, repo_root

        async def start_spawn(self, config: object) -> None:
            _ = config
            raise RuntimeError("boom")

        def subscribe(self, spawn_id: str) -> None:
            _ = spawn_id
            return None

        def unsubscribe(self, spawn_id: str) -> None:
            _ = spawn_id

        async def shutdown(
            self,
            *,
            status: str = "cancelled",
            exit_code: int = 1,
            error: str | None = None,
        ) -> None:
            _ = status, exit_code, error

    monkeypatch.setattr(streaming_serve_module, "SpawnManager", FakeManager)
    monkeypatch.setattr(
        streaming_serve_module,
        "resolve_runtime_root_and_config",
        lambda repo_root=None, *, sink=None: (repo_root or tmp_path, None),
    )
    monkeypatch.setattr(streaming_serve_module, "_install_signal_handlers", lambda *_: [])
    monkeypatch.setattr(streaming_serve_module, "_remove_signal_handlers", lambda *_: None)

    with pytest.raises(RuntimeError, match="boom"):
        await streaming_serve_module.streaming_serve("codex", "hello")

    events = _read_spawn_events(state_root)
    assert [event["event"] for event in events] == ["start", "finalize"]
    assert events[-1]["status"] == "failed"
    assert events[-1]["error"] == "boom"

    row = get_spawn(state_root, "p1")
    assert row is not None
    assert row.status == "failed"
    assert row.error == "boom"
