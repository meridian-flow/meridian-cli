from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_runtime_paths
from meridian.lib.state.reaper import reconcile_active_spawn

_OLD_STARTED_AT = "2000-01-01T00:00:00Z"


def _recent_started_at() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _state_root(tmp_path: Path) -> Path:
    state_root = resolve_runtime_paths(tmp_path).root_dir
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
) -> Path:
    report_path = state_root / "spawns" / spawn_id / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")
    return report_path


def _set_artifact_age_secs(path: Path, *, age_secs: float) -> None:
    target_epoch = time.time() - age_secs
    os.utime(path, (target_epoch, target_epoch))


def _write_activity_artifact(
    state_root: Path,
    spawn_id: str,
    artifact_name: str,
    *,
    age_secs: float,
) -> Path:
    artifact_path = state_root / "spawns" / spawn_id / artifact_name
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    if artifact_name == "heartbeat":
        artifact_path.touch()
    else:
        artifact_path.write_text("recent activity\n", encoding="utf-8")
    _set_artifact_age_secs(artifact_path, age_secs=age_secs)
    return artifact_path


def test_reconcile_active_spawn_returns_terminal_record_unchanged(
    tmp_path: Path,
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path, status="succeeded")
    record = _get_spawn(state_root, spawn_id)

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
    assert reconciled.error == "missing_runner_pid"
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "failed"
    assert latest.error == "missing_runner_pid"


def test_reconcile_active_spawn_returns_unchanged_when_runner_is_alive(
    tmp_path: Path, monkeypatch
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path)
    record = _get_spawn(state_root, spawn_id)
    monkeypatch.setattr(
        "meridian.lib.state.reaper.is_process_alive",
        lambda *_args, **_kwargs: True,
    )

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled == record
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "running"
    assert latest.error is None


def test_reconcile_active_spawn_finalizing_stale_heartbeat_marks_orphan_finalization(
    tmp_path: Path,
) -> None:
    state_root, spawn_id = _create_spawn(
        tmp_path,
        status="finalizing",
        started_at=_OLD_STARTED_AT,
    )
    _write_activity_artifact(
        state_root,
        spawn_id,
        "heartbeat",
        age_secs=300,
    )
    record = _get_spawn(state_root, spawn_id)
    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled.status == "failed"
    assert reconciled.exit_code == 1
    assert reconciled.error == "orphan_finalization"
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "failed"
    assert latest.error == "orphan_finalization"


@pytest.mark.parametrize("artifact_name", ["heartbeat", "stderr.log"])
def test_reconcile_active_spawn_finalizing_recent_activity_skips(
    tmp_path: Path,
    artifact_name: str,
) -> None:
    state_root, spawn_id = _create_spawn(
        tmp_path,
        status="finalizing",
        started_at=_OLD_STARTED_AT,
    )
    _write_activity_artifact(
        state_root,
        spawn_id,
        artifact_name,
        age_secs=5,
    )
    record = _get_spawn(state_root, spawn_id)
    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled == record
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "finalizing"
    assert latest.error is None


def test_reconcile_active_spawn_with_dead_runner_and_report_succeeds_without_exit_event(
    tmp_path: Path, monkeypatch
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path, started_at=_OLD_STARTED_AT)
    report_path = _write_report(state_root, spawn_id)
    _set_artifact_age_secs(report_path, age_secs=300)
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


@pytest.mark.parametrize(
    ("depth_value", "expected_status", "expected_error"),
    [
        ("1", "running", None),
        ("0", "failed", "missing_runner_pid"),
    ],
)
def test_reconcile_active_spawn_depth_gate_respects_env_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    depth_value: str,
    expected_status: str,
    expected_error: str | None,
) -> None:
    state_root, spawn_id = _create_spawn(
        tmp_path,
        runner_pid=None,
        started_at=_OLD_STARTED_AT,
    )
    record = _get_spawn(state_root, spawn_id)
    monkeypatch.setenv("MERIDIAN_DEPTH", depth_value)

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled.status == expected_status
    assert reconciled.error == expected_error
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == expected_status
    assert latest.error == expected_error
    if expected_status == "failed":
        assert reconciled.exit_code == 1
        assert latest.exit_code == 1


def test_reconcile_active_spawn_treats_exact_heartbeat_window_boundary_as_recent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path, started_at=_OLD_STARTED_AT)
    record = _get_spawn(state_root, spawn_id)
    heartbeat_path = state_root / "spawns" / spawn_id / "heartbeat"
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_path.touch()

    fixed_now = 1_000.0
    os.utime(heartbeat_path, (fixed_now - 120.0, fixed_now - 120.0))
    monkeypatch.setattr("meridian.lib.state.reaper.time.time", lambda: fixed_now)
    monkeypatch.setattr(
        "meridian.lib.state.reaper.is_process_alive",
        lambda *_args, **_kwargs: False,
    )

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled == record
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "running"
    assert latest.error is None


@pytest.mark.parametrize("artifact_name", ["heartbeat", "output.jsonl", "stderr.log", "report.md"])
def test_reconcile_active_spawn_dead_runner_recent_activity_skips_across_artifact_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact_name: str,
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path, started_at=_OLD_STARTED_AT)
    record = _get_spawn(state_root, spawn_id)
    _write_activity_artifact(
        state_root,
        spawn_id,
        artifact_name,
        age_secs=5,
    )

    fixed_now = time.time()
    monkeypatch.setattr("meridian.lib.state.reaper.time.time", lambda: fixed_now)
    monkeypatch.setattr(
        "meridian.lib.state.reaper.is_process_alive",
        lambda *_args, **_kwargs: False,
    )

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled == record
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "running"
    assert latest.error is None
