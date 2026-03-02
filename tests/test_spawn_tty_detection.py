"""spawn.create blocking execution TTY/pipe behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import meridian.lib.ops._spawn_execute as run_execute
import meridian.lib.ops.spawn as run_ops
from meridian.lib.ops.spawn import SpawnCreateInput
from meridian.lib.space.space_file import create_space


def _spawn_with_captured_stream_flags(
    *,
    monkeypatch,
    tmp_path: Path,
    stdout_is_tty: bool,
) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    async def fake_execute_with_finalization(*args: object, **kwargs: object) -> int:
        _ = args
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(run_ops, "execute_with_finalization", fake_execute_with_finalization)
    monkeypatch.setattr(run_execute, "_stdout_is_tty", lambda: stdout_is_tty)
    monkeypatch.setenv("MERIDIAN_SPACE_ID", create_space(tmp_path, name="tty").id)

    run_ops.spawn_create_sync(
        SpawnCreateInput(
            prompt="tty behavior",
            model="gpt-5.3-codex",
            repo_root=tmp_path.as_posix(),
        )
    )
    return captured


def test_run_create_non_tty_uses_event_filter(monkeypatch, tmp_path: Path) -> None:
    captured = _spawn_with_captured_stream_flags(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        stdout_is_tty=False,
    )
    # Non-TTY callers get filtered event output, not raw dumps.
    assert callable(captured["event_observer"])
    assert captured["stream_stdout_to_terminal"] is False
    assert captured["stream_stderr_to_terminal"] is False


def test_run_create_tty_uses_terminal_event_observer(monkeypatch, tmp_path: Path) -> None:
    captured = _spawn_with_captured_stream_flags(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        stdout_is_tty=True,
    )
    assert callable(captured["event_observer"])
    assert captured["stream_stdout_to_terminal"] is False
    assert captured["stream_stderr_to_terminal"] is False
