from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.state.reaper import reconcile_active_spawn

_OLD_STARTED_AT = "2000-01-01T00:00:00Z"


def _recent_started_at() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _state_root(tmp_path: Path) -> Path:
    state_root = resolve_state_paths(tmp_path).root_dir
    state_root.mkdir(parents=True, exist_ok=True)
    return state_root


def _create_spawn(
    tmp_path: Path,
    *,
    spawn_id: str = "p1",
    status: str = "running",
    runner_pid: int | None = 123,
    started_at: str | None = _OLD_STARTED_AT,
) -> tuple[Path, str]:
    state_root = _state_root(tmp_path)
    created_spawn_id = spawn_store.start_spawn(
        state_root,
        spawn_id=spawn_id,
        chat_id="c1",
        model="gpt-5.4",
        agent="tester",
        harness="codex",
        prompt="hello",
        status=status,
        runner_pid=runner_pid,
        started_at=started_at,
    )
    return state_root, str(created_spawn_id)


def _get_spawn(state_root: Path, spawn_id: str):
    record = spawn_store.get_spawn(state_root, spawn_id)
    assert record is not None
    return record


def _write_report(
    state_root: Path,
    spawn_id: str,
    text: str = "# Finished\n\nCompleted.\n",
) -> None:
    report_path = state_root / "spawns" / spawn_id / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")


def test_reconcile_active_spawn_returns_terminal_record_unchanged(
    tmp_path: Path, monkeypatch
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path, status="succeeded")
    record = _get_spawn(state_root, spawn_id)

    def _unexpected_call(pid: int, created_after_epoch: float | None = None) -> bool:
        raise AssertionError("is_process_alive should not run for terminal records")

    monkeypatch.setattr("meridian.lib.state.reaper.is_process_alive", _unexpected_call)

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled == record
    assert _get_spawn(state_root, spawn_id).status == "succeeded"


def test_reconcile_active_spawn_without_runner_pid_stays_unchanged_during_startup_grace(
    tmp_path: Path,
) -> None:
    state_root, spawn_id = _create_spawn(
        tmp_path,
        runner_pid=None,
        started_at=_recent_started_at(),
    )
    record = _get_spawn(state_root, spawn_id)

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled == record
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "running"
    assert latest.error is None


def test_reconcile_active_spawn_without_runner_pid_fails_after_startup_grace(
    tmp_path: Path,
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path, runner_pid=None, started_at=_OLD_STARTED_AT)
    record = _get_spawn(state_root, spawn_id)

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled.status == "failed"
    assert reconciled.exit_code == 1
    assert reconciled.error == "missing_worker_pid"
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "failed"
    assert latest.error == "missing_worker_pid"


def test_reconcile_active_spawn_returns_unchanged_when_runner_is_alive(
    tmp_path: Path, monkeypatch
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path)
    record = _get_spawn(state_root, spawn_id)
    seen: list[tuple[int, float | None]] = []

    def _alive(pid: int, created_after_epoch: float | None = None) -> bool:
        seen.append((pid, created_after_epoch))
        return True

    monkeypatch.setattr("meridian.lib.state.reaper.is_process_alive", _alive)

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled == record
    assert seen == [(123, 946684800.0)]
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "running"
    assert latest.error is None


def test_reconcile_active_spawn_marks_exited_spawn_with_report_succeeded(
    tmp_path: Path, monkeypatch
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path)
    spawn_store.record_spawn_exited(
        state_root,
        spawn_id,
        exit_code=0,
        exited_at="2026-04-12T14:00:00Z",
    )
    _write_report(state_root, spawn_id)
    record = _get_spawn(state_root, spawn_id)
    monkeypatch.setattr(
        "meridian.lib.state.reaper.is_process_alive",
        lambda *_args, **_kwargs: False,
    )

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled.status == "succeeded"
    assert reconciled.exit_code == 0
    assert reconciled.error is None
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "succeeded"
    assert latest.exit_code == 0
    assert latest.error is None


def test_reconcile_active_spawn_marks_exited_spawn_without_report_failed(
    tmp_path: Path, monkeypatch
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path)
    spawn_store.record_spawn_exited(
        state_root,
        spawn_id,
        exit_code=143,
        exited_at="2026-04-12T14:00:00Z",
    )
    record = _get_spawn(state_root, spawn_id)
    monkeypatch.setattr(
        "meridian.lib.state.reaper.is_process_alive",
        lambda *_args, **_kwargs: False,
    )

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled.status == "failed"
    assert reconciled.exit_code == 1
    assert reconciled.error == "orphan_finalization"
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "failed"
    assert latest.error == "orphan_finalization"


def test_reconcile_active_spawn_with_dead_runner_and_no_exit_stays_unchanged_in_grace(
    tmp_path: Path, monkeypatch
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path, started_at=_recent_started_at())
    record = _get_spawn(state_root, spawn_id)
    monkeypatch.setattr(
        "meridian.lib.state.reaper.is_process_alive",
        lambda *_args, **_kwargs: False,
    )

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled == record
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "running"
    assert latest.error is None


def test_reconcile_active_spawn_with_dead_runner_and_report_succeeds_without_exit_event(
    tmp_path: Path, monkeypatch
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path, started_at=_OLD_STARTED_AT)
    _write_report(state_root, spawn_id)
    record = _get_spawn(state_root, spawn_id)
    monkeypatch.setattr(
        "meridian.lib.state.reaper.is_process_alive",
        lambda *_args, **_kwargs: False,
    )

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled.status == "succeeded"
    assert reconciled.exit_code == 0
    assert reconciled.error is None
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "succeeded"
    assert latest.exit_code == 0
    assert latest.error is None


def test_reconcile_active_spawn_with_dead_runner_and_no_exit_or_report_fails(
    tmp_path: Path, monkeypatch
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path, started_at=_OLD_STARTED_AT)
    record = _get_spawn(state_root, spawn_id)
    monkeypatch.setattr(
        "meridian.lib.state.reaper.is_process_alive",
        lambda *_args, **_kwargs: False,
    )

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled.status == "failed"
    assert reconciled.exit_code == 1
    assert reconciled.error == "orphan_run"
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "failed"
    assert latest.error == "orphan_run"
