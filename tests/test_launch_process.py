from __future__ import annotations
# pyright: reportPrivateUsage=false

import os
import signal
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
from meridian.lib.state import spawn_store, work_store



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
        adapter=harness_registry.get_subprocess_harness(HarnessId.CODEX),
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
        seed_harness_session_id="session-2",
        command_request=request,
    )

    captured: dict[str, str | None] = {}

    def fake_build_launch_env(*args: object, **kwargs: object) -> dict[str, str]:
        _ = args
        captured["work_id_arg"] = kwargs.get("work_id")
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
    assert row.work_id == captured["work_id_arg"]
    assert row.work_id is None


def test_run_harness_process_attaches_explicit_work_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    harness_registry = get_default_harness_registry()
    config = load_config(repo_root)
    request = LaunchRequest(
        model="gpt-5.4",
        harness="codex",
        work_id="named-work",
    )
    plan = ResolvedPrimaryLaunchPlan(
        repo_root=repo_root,
        state_root=tmp_path / ".meridian",
        prompt="new prompt",
        request=request,
        config=config,
        adapter=harness_registry.get_subprocess_harness(HarnessId.CODEX),
        session_metadata=PrimarySessionMetadata(
            harness="codex",
            model="gpt-5.4",
            agent="",
            agent_path="",
            skills=(),
            skill_paths=(),
        ),
        run_params=SpawnParams(prompt="new prompt", model=ModelId("gpt-5.4"), interactive=True),
        permission_config=PermissionConfig(),
        command=("true",),
        seed_harness_session_id="session-3",
        command_request=request,
    )

    captured: dict[str, str | None] = {}

    def fake_build_launch_env(*args: object, **kwargs: object) -> dict[str, str]:
        _ = args
        captured["work_id_arg"] = kwargs.get("work_id")
        return {}

    def fake_run_primary_process_with_capture(**kwargs: object) -> tuple[int, int]:
        started = kwargs.get("on_child_started")
        assert callable(started)
        started(456)
        return (0, 456)

    def fake_start_session(
        state_root: Path,
        harness: str,
        harness_session_id: str | None,
        model: str,
        chat_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        _ = (state_root, harness, harness_session_id, model, kwargs)
        return chat_id or "c1"

    monkeypatch.setattr(process, "extract_latest_session_id", lambda **kwargs: "session-3")
    monkeypatch.setattr(process, "stop_session", lambda *args, **kwargs: None)
    monkeypatch.setattr(process, "update_session_harness_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(process, "build_launch_env", fake_build_launch_env)
    monkeypatch.setattr(process, "_run_primary_process_with_capture", fake_run_primary_process_with_capture)
    monkeypatch.setattr(process, "start_session", fake_start_session)

    outcome = process.run_harness_process(plan, harness_registry)

    row = spawn_store.get_spawn(plan.state_root, outcome.primary_spawn_id or "")
    assert row is not None
    assert row.work_id == "named-work"
    assert captured["work_id_arg"] == "named-work"
    assert work_store.get_work_item(plan.state_root, "named-work") is not None


