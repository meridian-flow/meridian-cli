import os
import subprocess
import time
from pathlib import Path

from meridian.lib.launch.process import active_primary_lock_path, primary_launch_lock
from meridian.lib.state import reaper
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.state.reaper import _recent_spawn_activity, _spawn_is_stale, reconcile_active_spawn
from meridian.lib.core.domain import SpawnStatus


_OLD_STARTED_AT = "2000-01-01T00:00:00Z"


def _start_background_spawn(
    tmp_path: Path,
    *,
    started_at: str | None = None,
    status: SpawnStatus = "queued",
) -> tuple[Path, str]:
    state_root = resolve_state_paths(tmp_path).root_dir
    spawn_id = spawn_store.start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="agent",
        harness="codex",
        kind="child",
        prompt="hello",
        launch_mode="background",
        status=status,
        started_at=started_at,
    )
    return state_root, str(spawn_id)


def _set_file_age(path: Path, *, age_seconds: int) -> None:
    old_time = time.time() - age_seconds
    os.utime(path, (old_time, old_time))


def test_reconcile_active_spawn_marks_missing_spawn_dir_failed_after_grace(tmp_path: Path) -> None:
    state_root, spawn_id = _start_background_spawn(tmp_path, started_at=_OLD_STARTED_AT)

    row = spawn_store.get_spawn(state_root, spawn_id)
    assert row is not None

    reconciled = reconcile_active_spawn(state_root, row)

    assert reconciled.status == "failed"
    assert reconciled.error == "missing_spawn_dir"
    latest = spawn_store.get_spawn(state_root, spawn_id)
    assert latest is not None
    assert latest.status == "failed"


def test_reconcile_active_spawn_marks_missing_pid_files_failed_after_grace(tmp_path: Path) -> None:
    state_root, spawn_id = _start_background_spawn(tmp_path, started_at=_OLD_STARTED_AT)
    spawn_dir = state_root / "spawns" / spawn_id
    spawn_dir.mkdir(parents=True, exist_ok=True)

    row = spawn_store.get_spawn(state_root, spawn_id)
    assert row is not None

    reconciled = reconcile_active_spawn(state_root, row)

    assert reconciled.status == "failed"
    assert reconciled.error == "missing_wrapper_pid"


def test_reconcile_active_spawn_promotes_queued_background_to_running_with_wrapper_pid(tmp_path: Path) -> None:
    state_root, spawn_id = _start_background_spawn(tmp_path, started_at=_OLD_STARTED_AT)
    spawn_dir = state_root / "spawns" / spawn_id
    spawn_dir.mkdir(parents=True, exist_ok=True)
    (spawn_dir / "background.pid").write_text(f"{os.getpid()}\n", encoding="utf-8")

    row = spawn_store.get_spawn(state_root, spawn_id)
    assert row is not None

    reconciled = reconcile_active_spawn(state_root, row)

    assert reconciled.status == "running"
    assert reconciled.wrapper_pid == os.getpid()
    latest = spawn_store.get_spawn(state_root, spawn_id)
    assert latest is not None
    assert latest.status == "running"
    assert latest.wrapper_pid == os.getpid()


def _start_foreground_spawn(
    tmp_path: Path,
    *,
    started_at: str | None = None,
    status: SpawnStatus = "running",
    worker_pid: int | None = None,
) -> tuple[Path, str]:
    state_root = resolve_state_paths(tmp_path).root_dir
    spawn_id = spawn_store.start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="agent",
        harness="codex",
        kind="child",
        prompt="hello",
        launch_mode="foreground",
        worker_pid=worker_pid,
        status=status,
        started_at=started_at,
    )
    return state_root, str(spawn_id)


def test_reconcile_background_spawn_with_report_and_dead_pid_succeeds(tmp_path: Path) -> None:
    """A background spawn with a dead PID but a valid report should succeed, not fail as orphan."""
    state_root, spawn_id = _start_background_spawn(tmp_path, started_at=_OLD_STARTED_AT, status="running")
    spawn_dir = state_root / "spawns" / spawn_id
    spawn_dir.mkdir(parents=True, exist_ok=True)
    dead_pid = 2_000_000_000
    (spawn_dir / "background.pid").write_text(f"{dead_pid}\n", encoding="utf-8")
    (spawn_dir / "report.md").write_text("# Finished\n\nCompleted.\n", encoding="utf-8")

    row = spawn_store.get_spawn(state_root, spawn_id)
    assert row is not None

    reconciled = reconcile_active_spawn(state_root, row)

    assert reconciled.status == "succeeded"
    assert reconciled.exit_code == 0
    assert reconciled.error is None
    latest = spawn_store.get_spawn(state_root, spawn_id)
    assert latest is not None
    assert latest.status == "succeeded"


def test_reconcile_background_spawn_with_report_and_live_wrapper_stays_running(tmp_path: Path) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    sleeper = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        spawn_id = spawn_store.start_spawn(
            state_root,
            chat_id="c1",
            model="gpt-5.4",
            agent="agent",
            harness="codex",
            kind="child",
            prompt="hello",
            launch_mode="background",
            status="running",
            started_at=_OLD_STARTED_AT,
        )
        spawn_dir = state_root / "spawns" / str(spawn_id)
        spawn_dir.mkdir(parents=True, exist_ok=True)
        (spawn_dir / "background.pid").write_text(f"{sleeper.pid}\n", encoding="utf-8")
        (spawn_dir / "report.md").write_text("# Finished\n\nCompleted.\n", encoding="utf-8")

        row = spawn_store.get_spawn(state_root, spawn_id)
        assert row is not None

        reconciled = reconcile_active_spawn(state_root, row)

        assert reconciled.status == "running"
        assert sleeper.poll() is None
        latest = spawn_store.get_spawn(state_root, spawn_id)
        assert latest is not None
        assert latest.status == "running"
        assert latest.exit_code is None
        assert latest.error is None
    finally:
        if sleeper.poll() is None:
            sleeper.terminate()
            sleeper.wait(timeout=5)


def test_reconcile_foreground_spawn_with_report_and_dead_pid_succeeds(tmp_path: Path) -> None:
    """A foreground spawn with a dead PID but a valid report should succeed, not fail as orphan."""
    dead_pid = 2_000_000_000
    state_root, spawn_id = _start_foreground_spawn(
        tmp_path, started_at=_OLD_STARTED_AT, worker_pid=dead_pid,
    )
    spawn_dir = state_root / "spawns" / spawn_id
    spawn_dir.mkdir(parents=True, exist_ok=True)
    (spawn_dir / "harness.pid").write_text(f"{dead_pid}\n", encoding="utf-8")
    (spawn_dir / "report.md").write_text("# Finished\n\nCompleted.\n", encoding="utf-8")

    row = spawn_store.get_spawn(state_root, spawn_id)
    assert row is not None

    reconciled = reconcile_active_spawn(state_root, row)

    assert reconciled.status == "succeeded"
    assert reconciled.exit_code == 0
    assert reconciled.error is None
    latest = spawn_store.get_spawn(state_root, spawn_id)
    assert latest is not None
    assert latest.status == "succeeded"


def test_reconcile_active_spawn_with_report_and_live_foreground_harness_stays_running(
    tmp_path: Path,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    sleeper = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        spawn_id = spawn_store.start_spawn(
            state_root,
            chat_id="c1",
            model="gpt-5.4",
            agent="agent",
            harness="codex",
            kind="child",
            prompt="hello",
            launch_mode="foreground",
            worker_pid=sleeper.pid,
            status="running",
            started_at=_OLD_STARTED_AT,
        )
        spawn_dir = state_root / "spawns" / str(spawn_id)
        spawn_dir.mkdir(parents=True, exist_ok=True)
        (spawn_dir / "harness.pid").write_text(f"{sleeper.pid}\n", encoding="utf-8")
        (spawn_dir / "report.md").write_text("# Finished\n\nCompleted.\n", encoding="utf-8")

        row = spawn_store.get_spawn(state_root, spawn_id)
        assert row is not None

        reconciled = reconcile_active_spawn(state_root, row)

        assert reconciled.status == "running"
        assert sleeper.poll() is None
        latest = spawn_store.get_spawn(state_root, spawn_id)
        assert latest is not None
        assert latest.status == "running"
        assert latest.exit_code is None
        assert latest.error is None
    finally:
        if sleeper.poll() is None:
            sleeper.terminate()
            sleeper.wait(timeout=5)


def test_reconcile_foreground_primary_queued_stays_queued_while_primary_lock_held(
    tmp_path: Path,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    spawn_id = spawn_store.start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="agent",
        harness="codex",
        kind="primary",
        prompt="hello",
        launch_mode="foreground",
        status="queued",
        started_at=_OLD_STARTED_AT,
    )
    spawn_dir = state_root / "spawns" / str(spawn_id)
    spawn_dir.mkdir(parents=True, exist_ok=True)
    row = spawn_store.get_spawn(state_root, spawn_id)
    assert row is not None

    lock_path = active_primary_lock_path(tmp_path)
    lock_payload = {
        "parent_pid": os.getpid(),
        "child_pid": None,
        "started_at": "2026-01-01T00:00:00Z",
        "command": ["codex"],
    }
    with primary_launch_lock(lock_path, lock_payload):
        reconciled = reconcile_active_spawn(state_root, row)

    assert reconciled.status == "queued"
    assert reconciled.error is None
    latest = spawn_store.get_spawn(state_root, spawn_id)
    assert latest is not None
    assert latest.status == "queued"
    assert latest.error is None


def test_stale_background_spawn_with_live_wrapper_is_preserved(tmp_path: Path, monkeypatch) -> None:
    state_root, spawn_id = _start_background_spawn(tmp_path, started_at=_OLD_STARTED_AT, status="running")
    spawn_dir = state_root / "spawns" / spawn_id
    spawn_dir.mkdir(parents=True, exist_ok=True)
    wrapper_pid = 12345
    (spawn_dir / "background.pid").write_text(f"{wrapper_pid}\n", encoding="utf-8")
    (spawn_dir / "output.jsonl").write_text("", encoding="utf-8")
    (spawn_dir / "stderr.log").write_text("", encoding="utf-8")
    _set_file_age(spawn_dir / "background.pid", age_seconds=301)
    _set_file_age(spawn_dir / "output.jsonl", age_seconds=301)
    _set_file_age(spawn_dir / "stderr.log", age_seconds=301)
    monkeypatch.setattr(reaper, "_pid_is_alive", lambda _pid, _pid_file: True)

    row = spawn_store.get_spawn(state_root, spawn_id)
    assert row is not None

    reconciled = reconcile_active_spawn(state_root, row)

    assert reconciled.status == "running"
    assert reconciled.error is None
    latest = spawn_store.get_spawn(state_root, spawn_id)
    assert latest is not None
    assert latest.status == "running"
    assert latest.error is None


def test_stale_foreground_spawn_with_live_harness_is_preserved(tmp_path: Path, monkeypatch) -> None:
    state_root, spawn_id = _start_foreground_spawn(tmp_path, started_at=_OLD_STARTED_AT, status="running")
    spawn_dir = state_root / "spawns" / spawn_id
    spawn_dir.mkdir(parents=True, exist_ok=True)
    harness_pid = 23456
    (spawn_dir / "harness.pid").write_text(f"{harness_pid}\n", encoding="utf-8")
    (spawn_dir / "output.jsonl").write_text("", encoding="utf-8")
    (spawn_dir / "stderr.log").write_text("", encoding="utf-8")
    _set_file_age(spawn_dir / "harness.pid", age_seconds=301)
    _set_file_age(spawn_dir / "output.jsonl", age_seconds=301)
    _set_file_age(spawn_dir / "stderr.log", age_seconds=301)
    monkeypatch.setattr(reaper, "_pid_is_alive", lambda _pid, _pid_file: True)

    row = spawn_store.get_spawn(state_root, spawn_id)
    assert row is not None

    reconciled = reconcile_active_spawn(state_root, row)

    assert reconciled.status == "running"
    assert reconciled.error is None
    latest = spawn_store.get_spawn(state_root, spawn_id)
    assert latest is not None
    assert latest.status == "running"
    assert latest.error is None


def test_stale_dead_background_spawn_is_finalized(tmp_path: Path, monkeypatch) -> None:
    state_root, spawn_id = _start_background_spawn(tmp_path, started_at=_OLD_STARTED_AT, status="running")
    spawn_dir = state_root / "spawns" / spawn_id
    spawn_dir.mkdir(parents=True, exist_ok=True)
    (spawn_dir / "background.pid").write_text("12345\n", encoding="utf-8")
    (spawn_dir / "harness.pid").write_text("23456\n", encoding="utf-8")
    (spawn_dir / "output.jsonl").write_text("", encoding="utf-8")
    (spawn_dir / "stderr.log").write_text("", encoding="utf-8")
    _set_file_age(spawn_dir / "background.pid", age_seconds=301)
    _set_file_age(spawn_dir / "harness.pid", age_seconds=301)
    _set_file_age(spawn_dir / "output.jsonl", age_seconds=301)
    _set_file_age(spawn_dir / "stderr.log", age_seconds=301)
    monkeypatch.setattr(reaper, "_pid_is_alive", lambda _pid, _pid_file: False)

    row = spawn_store.get_spawn(state_root, spawn_id)
    assert row is not None

    reconciled = reconcile_active_spawn(state_root, row)

    assert reconciled.status == "failed"
    assert reconciled.error == "orphan_run"
    latest = spawn_store.get_spawn(state_root, spawn_id)
    assert latest is not None
    assert latest.status == "failed"
    assert latest.error == "orphan_run"


def test_stale_dead_foreground_spawn_is_finalized(tmp_path: Path, monkeypatch) -> None:
    state_root, spawn_id = _start_foreground_spawn(tmp_path, started_at=_OLD_STARTED_AT, status="running")
    spawn_dir = state_root / "spawns" / spawn_id
    spawn_dir.mkdir(parents=True, exist_ok=True)
    (spawn_dir / "harness.pid").write_text("34567\n", encoding="utf-8")
    (spawn_dir / "output.jsonl").write_text("", encoding="utf-8")
    (spawn_dir / "stderr.log").write_text("", encoding="utf-8")
    _set_file_age(spawn_dir / "harness.pid", age_seconds=301)
    _set_file_age(spawn_dir / "output.jsonl", age_seconds=301)
    _set_file_age(spawn_dir / "stderr.log", age_seconds=301)
    monkeypatch.setattr(reaper, "_pid_is_alive", lambda _pid, _pid_file: False)

    row = spawn_store.get_spawn(state_root, spawn_id)
    assert row is not None

    reconciled = reconcile_active_spawn(state_root, row)

    assert reconciled.status == "failed"
    assert reconciled.error == "orphan_run"
    latest = spawn_store.get_spawn(state_root, spawn_id)
    assert latest is not None
    assert latest.status == "failed"
    assert latest.error == "orphan_run"


def test_heartbeat_prevents_stale_detection(tmp_path: Path) -> None:
    spawn_dir = tmp_path / "spawn"
    spawn_dir.mkdir(parents=True, exist_ok=True)
    pid_file = spawn_dir / "background.pid"
    pid_file.write_text("12345\n", encoding="utf-8")
    (spawn_dir / "output.jsonl").write_text("", encoding="utf-8")
    (spawn_dir / "stderr.log").write_text("", encoding="utf-8")
    heartbeat = spawn_dir / "heartbeat"
    heartbeat.write_text("", encoding="utf-8")
    _set_file_age(pid_file, age_seconds=301)
    _set_file_age(spawn_dir / "output.jsonl", age_seconds=301)
    _set_file_age(spawn_dir / "stderr.log", age_seconds=301)
    os.utime(heartbeat, None)

    assert _spawn_is_stale(spawn_dir, pid_file) is False


def test_reconcile_background_dead_wrapper_live_harness_with_report_succeeds(
    tmp_path: Path, monkeypatch,
) -> None:
    """Dead wrapper + live harness + report.md → finalize as succeeded.

    The wrapper is the coordinator; if it's dead, nobody will finalize.
    The report proves the work completed, so the orphaned harness is harmless.
    """
    state_root, spawn_id = _start_background_spawn(tmp_path, started_at=_OLD_STARTED_AT, status="running")
    spawn_dir = state_root / "spawns" / spawn_id
    spawn_dir.mkdir(parents=True, exist_ok=True)
    dead_wrapper = 2_000_000_000
    live_harness = 2_000_000_001
    (spawn_dir / "background.pid").write_text(f"{dead_wrapper}\n", encoding="utf-8")
    (spawn_dir / "harness.pid").write_text(f"{live_harness}\n", encoding="utf-8")
    (spawn_dir / "report.md").write_text("# Finished\n\nCompleted.\n", encoding="utf-8")

    def _selective_alive(pid: int, _pid_file: Path) -> bool:
        return pid == live_harness

    monkeypatch.setattr(reaper, "_pid_is_alive", _selective_alive)

    row = spawn_store.get_spawn(state_root, spawn_id)
    assert row is not None

    reconciled = reconcile_active_spawn(state_root, row)

    assert reconciled.status == "succeeded"
    assert reconciled.exit_code == 0


def test_heartbeat_in_recent_spawn_activity(tmp_path: Path) -> None:
    spawn_dir = tmp_path / "spawn"
    spawn_dir.mkdir(parents=True, exist_ok=True)
    heartbeat = spawn_dir / "heartbeat"
    heartbeat.write_text("", encoding="utf-8")
    now = time.time()

    assert _recent_spawn_activity(spawn_dir, now=now) is True
