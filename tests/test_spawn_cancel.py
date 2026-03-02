"""spawn.cancel operation behavior."""

from __future__ import annotations

import os
import signal
from pathlib import Path

import pytest

from meridian.lib.ops.spawn import SpawnCancelInput, spawn_cancel_sync
from meridian.lib.space.space_file import create_space
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_space_dir


def _start_running_spawn(space_dir: Path) -> str:
    spawn_id = spawn_store.start_spawn(
        space_dir,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        prompt="cancel me",
    )
    return str(spawn_id)


def test_spawn_cancel_signals_pid_and_finalizes_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space = create_space(tmp_path, name="cancel")
    space_dir = resolve_space_dir(tmp_path, space.id)
    spawn_id = _start_running_spawn(space_dir)
    pid_path = space_dir / "spawns" / spawn_id / "background.pid"
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("4242\n", encoding="utf-8")

    calls: list[tuple[int, signal.Signals]] = []

    def fake_kill(pid: int, sig: int) -> None:
        calls.append((pid, signal.Signals(sig)))

    monkeypatch.setattr(os, "kill", fake_kill)

    result = spawn_cancel_sync(
        SpawnCancelInput(
            spawn_id=spawn_id,
            space=space.id,
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.command == "spawn.cancel"
    assert result.status == "cancelled"
    assert calls == [(4242, signal.SIGTERM)]
    row = spawn_store.get_spawn(space_dir, spawn_id)
    assert row is not None
    assert row.status == "cancelled"
    assert row.error == "cancelled"
    assert row.exit_code == 130


def test_spawn_cancel_tolerates_missing_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space = create_space(tmp_path, name="cancel-missing-pid")
    space_dir = resolve_space_dir(tmp_path, space.id)
    spawn_id = _start_running_spawn(space_dir)
    pid_path = space_dir / "spawns" / spawn_id / "background.pid"
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("31337\n", encoding="utf-8")

    def fake_kill(pid: int, sig: int) -> None:
        _ = (pid, sig)
        raise ProcessLookupError

    monkeypatch.setattr(os, "kill", fake_kill)

    result = spawn_cancel_sync(
        SpawnCancelInput(
            spawn_id=spawn_id,
            space=space.id,
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.status == "cancelled"
    row = spawn_store.get_spawn(space_dir, spawn_id)
    assert row is not None
    assert row.status == "cancelled"


def test_spawn_cancel_returns_noop_for_terminal_spawn(tmp_path: Path) -> None:
    space = create_space(tmp_path, name="cancel-terminal")
    space_dir = resolve_space_dir(tmp_path, space.id)
    spawn_id = _start_running_spawn(space_dir)
    spawn_store.finalize_spawn(space_dir, spawn_id, "succeeded", 0)

    result = spawn_cancel_sync(
        SpawnCancelInput(
            spawn_id=spawn_id,
            space=space.id,
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.status == "succeeded"
    assert result.message == f"Spawn '{spawn_id}' is already succeeded."
