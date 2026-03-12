from __future__ import annotations
# pyright: reportPrivateUsage=false

import fcntl
import multiprocessing as mp
import os
import signal
import time
import json
from pathlib import Path
from typing import Any

import pytest

from meridian.lib.launch import process
from meridian.lib.launch.plan import ResolvedPrimaryLaunchPlan
from meridian.lib.launch.types import LaunchRequest, PrimarySessionMetadata
from meridian.lib.config.settings import load_config
from meridian.lib.core.types import HarnessId, ModelId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.safety.permissions import PermissionConfig
from meridian.lib.state import spawn_store


def _attempt_primary_launch_lock(lock_path_str: str, hold_secs: float, queue: Any) -> None:
    start = time.monotonic()
    payload = {
        "parent_pid": os.getpid(),
        "child_pid": None,
        "started_at": "2000-01-01T00:00:00Z",
        "command": ["sleep", "1"],
    }
    try:
        with process.primary_launch_lock(Path(lock_path_str), payload):
            queue.put(("acquired", time.monotonic() - start))
            if hold_secs > 0:
                time.sleep(hold_secs)
    except ValueError:
        queue.put(("contended", time.monotonic() - start))
    except Exception as exc:  # pragma: no cover - defensive test helper guard
        queue.put(("error", repr(exc)))


def test_sync_pty_winsize_copies_source_size(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int, bytes]] = []
    packed = b"winsize-bytes"

    def fake_ioctl(fd: int, op: int, payload: bytes) -> bytes:
        calls.append((fd, op, payload))
        if op == process.termios.TIOCGWINSZ:
            return packed
        return b""

    monkeypatch.setattr(process.fcntl, "ioctl", fake_ioctl)

    process._sync_pty_winsize(source_fd=10, target_fd=11)

    assert calls == [
        (10, process.termios.TIOCGWINSZ, process.struct.pack("HHHH", 0, 0, 0, 0)),
        (11, process.termios.TIOCSWINSZ, packed),
    ]


def test_install_winsize_forwarding_syncs_immediately_and_restores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_calls: list[tuple[int, int]] = []
    installed_handlers: list[tuple[int, object]] = []
    previous_handler = signal.SIG_IGN

    def fake_sync_pty_winsize(*, source_fd: int, target_fd: int) -> None:
        sync_calls.append((source_fd, target_fd))

    def fake_getsignal(signum: int) -> object:
        _ = signum
        return previous_handler

    def fake_signal(signum: int, handler: object) -> None:
        installed_handlers.append((signum, handler))

    monkeypatch.setattr(
        process,
        "_sync_pty_winsize",
        fake_sync_pty_winsize,
    )
    monkeypatch.setattr(process.signal, "getsignal", fake_getsignal)
    monkeypatch.setattr(process.signal, "signal", fake_signal)

    restore = process._install_winsize_forwarding(source_fd=20, target_fd=21)

    assert sync_calls == [(20, 21)]
    assert installed_handlers[0][0] == signal.SIGWINCH

    handler = installed_handlers[0][1]
    assert callable(handler)
    handler(signal.SIGWINCH, None)

    assert sync_calls == [(20, 21), (20, 21)]

    restore()

    assert installed_handlers[-1] == (signal.SIGWINCH, previous_handler)


def test_run_harness_process_reuses_tracked_chat_id_on_resume(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    harness_registry = get_default_harness_registry()
    config = load_config(repo_root)
    request = LaunchRequest(
        model="gpt-5.4",
        harness="codex",
        fresh=False,
        continue_harness_session_id="session-2",
        continue_chat_id="c7",
    )
    plan = ResolvedPrimaryLaunchPlan(
        repo_root=repo_root,
        state_root=tmp_path / ".meridian",
        prompt="resume prompt",
        request=request,
        config=config,
        adapter=harness_registry.get_subprocess_harness(HarnessId("codex")),
        session_metadata=PrimarySessionMetadata(
            harness="codex",
            model="gpt-5.4",
            agent="",
            agent_path="",
            skills=(),
            skill_paths=(),
        ),
        run_params=SpawnParams(prompt="resume prompt", model=ModelId("gpt-5.4"), interactive=True),
        permission_config=PermissionConfig(),
        command=("true",),
        lock_path=tmp_path / ".meridian" / "active-primary.lock",
        seed_harness_session_id="session-2",
        command_request=request,
    )

    captured: dict[str, str | None] = {}

    def fake_sweep_orphaned_materializations(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)

    def fake_build_launch_env(*args: object, **kwargs: object) -> dict[str, str]:
        _ = (args, kwargs)
        return {}

    def fake_run_primary_process_with_capture(**kwargs: object) -> tuple[int, int]:
        started = kwargs.get("on_child_started")
        assert callable(started)
        started(123)
        return (0, 123)

    def fake_extract_latest_session_id(**kwargs: object) -> str:
        _ = kwargs
        return "session-2"

    def fake_stop_session(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)

    def fake_update_session_harness_id(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)

    monkeypatch.setattr(
        process,
        "_sweep_orphaned_materializations",
        fake_sweep_orphaned_materializations,
    )
    monkeypatch.setattr(process, "build_launch_env", fake_build_launch_env)
    monkeypatch.setattr(
        process,
        "_run_primary_process_with_capture",
        fake_run_primary_process_with_capture,
    )
    monkeypatch.setattr(process, "extract_latest_session_id", fake_extract_latest_session_id)
    monkeypatch.setattr(process, "stop_session", fake_stop_session)
    monkeypatch.setattr(process, "update_session_harness_id", fake_update_session_harness_id)

    def fake_start_session(
        state_root: Path,
        harness: str,
        harness_session_id: str | None,
        model: str,
        chat_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        _ = (state_root, harness, harness_session_id, model, kwargs)
        captured["chat_id_arg"] = chat_id
        return chat_id or "c999"

    monkeypatch.setattr(process, "start_session", fake_start_session)

    outcome = process.run_harness_process(plan, harness_registry)

    assert captured["chat_id_arg"] == "c7"
    assert outcome.chat_id == "c7"
    assert outcome.primary_spawn_id is not None
    row = spawn_store.get_spawn(plan.state_root, outcome.primary_spawn_id)
    assert row is not None
    assert row.worker_pid == 123


def test_primary_launch_lock_acquires_and_releases(tmp_path: Path) -> None:
    lock_path = process.active_primary_lock_path(tmp_path)
    first_payload = {
        "parent_pid": os.getpid(),
        "child_pid": None,
        "started_at": "2026-01-01T00:00:00Z",
        "command": ["first"],
    }
    second_payload = {
        "parent_pid": os.getpid(),
        "child_pid": 999,
        "started_at": "2026-01-01T00:00:01Z",
        "command": ["second"],
    }

    with process.primary_launch_lock(lock_path, first_payload):
        assert lock_path.is_file()
        assert json.loads(lock_path.read_text(encoding="utf-8")) == first_payload

    with process.primary_launch_lock(lock_path, second_payload):
        assert json.loads(lock_path.read_text(encoding="utf-8")) == second_payload


def test_primary_launch_lock_raises_value_error_on_contention(tmp_path: Path) -> None:
    lock_path = process.active_primary_lock_path(tmp_path)
    payload = {
        "parent_pid": os.getpid(),
        "child_pid": None,
        "started_at": "2026-01-01T00:00:00Z",
        "command": ["contention"],
    }

    with process.primary_launch_lock(lock_path, payload):
        with pytest.raises(ValueError, match="already active"):
            with process.primary_launch_lock(lock_path, payload):
                pass


def test_primary_launch_lock_contends_across_processes(tmp_path: Path) -> None:
    start_method = "fork" if "fork" in mp.get_all_start_methods() else "spawn"
    ctx = mp.get_context(start_method)
    queue = ctx.Queue()
    lock_path = process.active_primary_lock_path(tmp_path)

    first = ctx.Process(target=_attempt_primary_launch_lock, args=(str(lock_path), 2.0, queue))
    second = ctx.Process(target=_attempt_primary_launch_lock, args=(str(lock_path), 0.0, queue))
    first.start()
    first_status, _ = queue.get(timeout=5)
    assert first_status == "acquired"

    second.start()
    second_status, second_elapsed = queue.get(timeout=5)
    assert second_status == "contended"
    assert second_elapsed < 1.0

    second.join(timeout=10)
    first.join(timeout=10)
    assert second.exitcode == 0
    assert first.exitcode == 0


def test_cleanup_orphaned_locks_removes_unheld_lock_file(tmp_path: Path) -> None:
    lock_path = process.active_primary_lock_path(tmp_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text('{"stale": true}\n', encoding="utf-8")

    assert process.cleanup_orphaned_locks(tmp_path) is True
    assert not lock_path.exists()


def test_cleanup_orphaned_locks_keeps_live_flock(tmp_path: Path) -> None:
    lock_path = process.active_primary_lock_path(tmp_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        handle.seek(0)
        handle.truncate()
        handle.write('{"live": true}\n')
        handle.flush()

        assert process.cleanup_orphaned_locks(tmp_path) is False
        assert lock_path.exists()

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
