from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_runtime_paths
from meridian.lib.state.reaper import (
    ArtifactSnapshot,
    FinalizeFailed,
    FinalizeSucceededFromReport,
    Skip,
    decide_reconciliation,
    reconcile_active_spawn,
)

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
    assert reconciled.error == "missing_runner_pid"
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "failed"
    assert latest.error == "missing_runner_pid"


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


def test_reconcile_active_spawn_marks_running_spawn_without_report_failed(
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
    assert reconciled.error == "orphan_run"
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "failed"
    assert latest.error == "orphan_run"


def test_reconcile_active_spawn_finalizing_stale_heartbeat_marks_orphan_finalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root, spawn_id = _create_spawn(
        tmp_path,
        status="finalizing",
        started_at=_OLD_STARTED_AT,
    )
    heartbeat_path = state_root / "spawns" / spawn_id / "heartbeat"
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_path.touch()
    _set_artifact_age_secs(heartbeat_path, age_secs=300)

    def _unexpected_probe(*_args, **_kwargs) -> bool:
        raise AssertionError("is_process_alive should not run for finalizing rows")

    monkeypatch.setattr("meridian.lib.state.reaper.is_process_alive", _unexpected_probe)
    record = _get_spawn(state_root, spawn_id)
    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled.status == "failed"
    assert reconciled.exit_code == 1
    assert reconciled.error == "orphan_finalization"
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "failed"
    assert latest.error == "orphan_finalization"


def test_reconcile_active_spawn_finalizing_recent_heartbeat_skips(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root, spawn_id = _create_spawn(
        tmp_path,
        status="finalizing",
        started_at=_OLD_STARTED_AT,
    )
    heartbeat_path = state_root / "spawns" / spawn_id / "heartbeat"
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_path.touch()
    _set_artifact_age_secs(heartbeat_path, age_secs=5)

    def _unexpected_probe(*_args, **_kwargs) -> bool:
        raise AssertionError("is_process_alive should not run for finalizing rows")

    monkeypatch.setattr("meridian.lib.state.reaper.is_process_alive", _unexpected_probe)
    record = _get_spawn(state_root, spawn_id)
    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled == record
    latest = _get_spawn(state_root, spawn_id)
    assert latest.status == "finalizing"
    assert latest.error is None


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


def test_decide_reconciliation_recent_heartbeat_skips() -> None:
    record = spawn_store.SpawnRecord(
        id="p1",
        chat_id=None,
        parent_id=None,
        model=None,
        agent=None,
        agent_path=None,
        skills=(),
        skill_paths=(),
        harness=None,
        kind="child",
        desc=None,
        work_id=None,
        harness_session_id=None,
        execution_cwd=None,
        launch_mode=None,
        worker_pid=None,
        runner_pid=123,
        status="running",
        prompt=None,
        started_at=_OLD_STARTED_AT,
        exited_at=None,
        process_exit_code=None,
        finished_at=None,
        exit_code=None,
        duration_secs=None,
        total_cost_usd=None,
        input_tokens=None,
        output_tokens=None,
        error=None,
        terminal_origin=None,
    )
    now = 1_000.0
    snapshot = ArtifactSnapshot(
        started_epoch=900.0,
        last_activity_epoch=now - 5.0,
        recent_activity_artifact="heartbeat",
        durable_report_completion=False,
        runner_pid_alive=False,
    )

    decision = decide_reconciliation(record, snapshot, now)

    assert isinstance(decision, Skip)
    assert decision.reason == "recent_activity"


def test_decide_reconciliation_stale_dead_runner_fails_orphan_run() -> None:
    record = spawn_store.SpawnRecord(
        id="p1",
        chat_id=None,
        parent_id=None,
        model=None,
        agent=None,
        agent_path=None,
        skills=(),
        skill_paths=(),
        harness=None,
        kind="child",
        desc=None,
        work_id=None,
        harness_session_id=None,
        execution_cwd=None,
        launch_mode=None,
        worker_pid=None,
        runner_pid=123,
        status="running",
        prompt=None,
        started_at=_OLD_STARTED_AT,
        exited_at=None,
        process_exit_code=None,
        finished_at=None,
        exit_code=None,
        duration_secs=None,
        total_cost_usd=None,
        input_tokens=None,
        output_tokens=None,
        error=None,
        terminal_origin=None,
    )
    now = 1_000.0
    snapshot = ArtifactSnapshot(
        started_epoch=900.0,
        last_activity_epoch=700.0,
        recent_activity_artifact=None,
        durable_report_completion=False,
        runner_pid_alive=False,
    )

    decision = decide_reconciliation(record, snapshot, now)

    assert isinstance(decision, FinalizeFailed)
    assert decision.error == "orphan_run"


def test_decide_reconciliation_dead_runner_accepts_fallback_recent_activity() -> None:
    record = spawn_store.SpawnRecord(
        id="p1",
        chat_id=None,
        parent_id=None,
        model=None,
        agent=None,
        agent_path=None,
        skills=(),
        skill_paths=(),
        harness=None,
        kind="child",
        desc=None,
        work_id=None,
        harness_session_id=None,
        execution_cwd=None,
        launch_mode=None,
        worker_pid=None,
        runner_pid=123,
        status="running",
        prompt=None,
        started_at=_OLD_STARTED_AT,
        exited_at=None,
        process_exit_code=None,
        finished_at=None,
        exit_code=None,
        duration_secs=None,
        total_cost_usd=None,
        input_tokens=None,
        output_tokens=None,
        error=None,
        terminal_origin=None,
    )
    now = 1_000.0
    snapshot = ArtifactSnapshot(
        started_epoch=900.0,
        last_activity_epoch=now - 5.0,
        recent_activity_artifact="stderr.log",
        durable_report_completion=False,
        runner_pid_alive=False,
    )

    decision = decide_reconciliation(record, snapshot, now)

    assert isinstance(decision, Skip)
    assert decision.reason == "recent_activity"


def test_decide_reconciliation_live_runner_accepts_fallback_recent_activity() -> None:
    record = spawn_store.SpawnRecord(
        id="p1",
        chat_id=None,
        parent_id=None,
        model=None,
        agent=None,
        agent_path=None,
        skills=(),
        skill_paths=(),
        harness=None,
        kind="child",
        desc=None,
        work_id=None,
        harness_session_id=None,
        execution_cwd=None,
        launch_mode=None,
        worker_pid=None,
        runner_pid=123,
        status="running",
        prompt=None,
        started_at=_OLD_STARTED_AT,
        exited_at=None,
        process_exit_code=None,
        finished_at=None,
        exit_code=None,
        duration_secs=None,
        total_cost_usd=None,
        input_tokens=None,
        output_tokens=None,
        error=None,
        terminal_origin=None,
    )
    now = 1_000.0
    snapshot = ArtifactSnapshot(
        started_epoch=900.0,
        last_activity_epoch=now - 5.0,
        recent_activity_artifact="stderr.log",
        durable_report_completion=False,
        runner_pid_alive=True,
    )

    decision = decide_reconciliation(record, snapshot, now)

    assert isinstance(decision, Skip)
    assert decision.reason == "recent_activity"


def test_decide_reconciliation_durable_report_succeeds() -> None:
    record = spawn_store.SpawnRecord(
        id="p1",
        chat_id=None,
        parent_id=None,
        model=None,
        agent=None,
        agent_path=None,
        skills=(),
        skill_paths=(),
        harness=None,
        kind="child",
        desc=None,
        work_id=None,
        harness_session_id=None,
        execution_cwd=None,
        launch_mode=None,
        worker_pid=None,
        runner_pid=123,
        status="running",
        prompt=None,
        started_at=_OLD_STARTED_AT,
        exited_at=None,
        process_exit_code=None,
        finished_at=None,
        exit_code=None,
        duration_secs=None,
        total_cost_usd=None,
        input_tokens=None,
        output_tokens=None,
        error=None,
        terminal_origin=None,
    )
    snapshot = ArtifactSnapshot(
        started_epoch=900.0,
        last_activity_epoch=700.0,
        recent_activity_artifact=None,
        durable_report_completion=True,
        runner_pid_alive=False,
    )

    decision = decide_reconciliation(record, snapshot, now=1_000.0)

    assert isinstance(decision, FinalizeSucceededFromReport)


def test_reconcile_active_spawn_depth_gate_skips_snapshot_and_finalize(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path, started_at=_OLD_STARTED_AT)
    record = _get_spawn(state_root, spawn_id)
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")

    def _unexpected_collect(*_args, **_kwargs):
        raise AssertionError("_collect_artifact_snapshot should not run under depth gate")

    monkeypatch.setattr("meridian.lib.state.reaper._collect_artifact_snapshot", _unexpected_collect)
    monkeypatch.setattr(
        "meridian.lib.state.reaper.finalize_spawn",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("finalize_spawn should not run under depth gate")
        ),
    )

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled == record


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
    monkeypatch.setattr(
        "meridian.lib.state.reaper.finalize_spawn",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("finalize_spawn should not run inside the heartbeat window")
        ),
    )

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled == record


@pytest.mark.parametrize("artifact_name", ["output.jsonl", "stderr.log", "report.md"])
def test_reconcile_active_spawn_treats_recent_fallback_artifact_as_recent_when_runner_is_dead(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact_name: str,
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path, started_at=_OLD_STARTED_AT)
    record = _get_spawn(state_root, spawn_id)
    artifact_path = state_root / "spawns" / spawn_id / artifact_name
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("recent activity\n", encoding="utf-8")

    fixed_now = time.time()
    os.utime(artifact_path, (fixed_now - 5.0, fixed_now - 5.0))
    monkeypatch.setattr("meridian.lib.state.reaper.time.time", lambda: fixed_now)
    monkeypatch.setattr(
        "meridian.lib.state.reaper.is_process_alive",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "meridian.lib.state.reaper.finalize_spawn",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("finalize_spawn should not run inside the activity window")
        ),
    )

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled == record


@pytest.mark.parametrize("artifact_name", ["output.jsonl", "stderr.log"])
def test_reconcile_active_spawn_treats_recent_fallback_artifact_as_recent_when_runner_is_alive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact_name: str,
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path, started_at=_OLD_STARTED_AT)
    record = _get_spawn(state_root, spawn_id)
    artifact_path = state_root / "spawns" / spawn_id / artifact_name
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("recent activity\n", encoding="utf-8")

    fixed_now = time.time()
    os.utime(artifact_path, (fixed_now - 5.0, fixed_now - 5.0))
    monkeypatch.setattr("meridian.lib.state.reaper.time.time", lambda: fixed_now)
    monkeypatch.setattr(
        "meridian.lib.state.reaper.is_process_alive",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "meridian.lib.state.reaper.finalize_spawn",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("finalize_spawn should not run when runner is alive")
        ),
    )

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled == record


def test_reconcile_active_spawn_skips_when_dead_runner_has_recent_heartbeat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path, started_at=_OLD_STARTED_AT)
    record = _get_spawn(state_root, spawn_id)
    heartbeat_path = state_root / "spawns" / spawn_id / "heartbeat"
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_path.touch()

    fixed_now = time.time()
    os.utime(heartbeat_path, (fixed_now - 5.0, fixed_now - 5.0))
    monkeypatch.setattr("meridian.lib.state.reaper.time.time", lambda: fixed_now)
    monkeypatch.setattr(
        "meridian.lib.state.reaper.is_process_alive",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "meridian.lib.state.reaper.finalize_spawn",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("finalize_spawn should not run for recent heartbeat")
        ),
    )

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled == record


def test_reconcile_active_spawn_ignores_recent_fallback_artifact_without_runner_pid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root, spawn_id = _create_spawn(
        tmp_path,
        runner_pid=None,
        started_at=_OLD_STARTED_AT,
    )
    record = _get_spawn(state_root, spawn_id)
    stderr_path = state_root / "spawns" / spawn_id / "stderr.log"
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.write_text("recent stderr\n", encoding="utf-8")

    fixed_now = time.time()
    os.utime(stderr_path, (fixed_now - 5.0, fixed_now - 5.0))
    monkeypatch.setattr("meridian.lib.state.reaper.time.time", lambda: fixed_now)
    monkeypatch.setattr(
        "meridian.lib.state.reaper.finalize_spawn",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("finalize_spawn should not run inside the activity window")
        ),
    )

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled == record


def test_reconcile_active_spawn_finalizing_recent_fallback_artifact_skips(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root, spawn_id = _create_spawn(
        tmp_path,
        status="finalizing",
        started_at=_OLD_STARTED_AT,
    )
    stderr_path = state_root / "spawns" / spawn_id / "stderr.log"
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.write_text("recent stderr\n", encoding="utf-8")

    fixed_now = time.time()
    os.utime(stderr_path, (fixed_now - 5.0, fixed_now - 5.0))
    monkeypatch.setattr("meridian.lib.state.reaper.time.time", lambda: fixed_now)
    monkeypatch.setattr(
        "meridian.lib.state.reaper.finalize_spawn",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("finalize_spawn should not run inside the activity window")
        ),
    )
    monkeypatch.setattr(
        "meridian.lib.state.reaper.is_process_alive",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("is_process_alive should not run for finalizing rows")
        ),
    )

    record = _get_spawn(state_root, spawn_id)
    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled == record


def test_reconcile_active_spawn_depth_zero_still_collects_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path, started_at=_OLD_STARTED_AT)
    record = _get_spawn(state_root, spawn_id)
    monkeypatch.setenv("MERIDIAN_DEPTH", "0")
    collected: list[tuple[Path, str, float]] = []

    def _collect(state_root_arg: Path, record_arg, now: float) -> ArtifactSnapshot:
        collected.append((state_root_arg, record_arg.id, now))
        return ArtifactSnapshot(
            started_epoch=900.0,
            last_activity_epoch=None,
            recent_activity_artifact=None,
            durable_report_completion=False,
            runner_pid_alive=True,
        )

    monkeypatch.setattr("meridian.lib.state.reaper._collect_artifact_snapshot", _collect)

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled == record
    assert len(collected) == 1
    assert collected[0][0] == state_root
    assert collected[0][1] == spawn_id


def test_decide_reconciliation_is_pure_after_snapshot_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = spawn_store.SpawnRecord(
        id="p1",
        chat_id=None,
        parent_id=None,
        model=None,
        agent=None,
        agent_path=None,
        skills=(),
        skill_paths=(),
        harness=None,
        kind="child",
        desc=None,
        work_id=None,
        harness_session_id=None,
        execution_cwd=None,
        launch_mode=None,
        worker_pid=None,
        runner_pid=123,
        status="running",
        prompt=None,
        started_at=_OLD_STARTED_AT,
        exited_at=None,
        process_exit_code=None,
        finished_at=None,
        exit_code=None,
        duration_secs=None,
        total_cost_usd=None,
        input_tokens=None,
        output_tokens=None,
        error=None,
        terminal_origin=None,
    )
    snapshot = ArtifactSnapshot(
        started_epoch=900.0,
        last_activity_epoch=700.0,
        recent_activity_artifact=None,
        durable_report_completion=False,
        runner_pid_alive=False,
    )

    def _unexpected_stat(self: Path) -> object:
        raise AssertionError("decide_reconciliation must not perform filesystem I/O")

    monkeypatch.setattr(Path, "stat", _unexpected_stat)

    decision = decide_reconciliation(record, snapshot, now=1_000.0)

    assert isinstance(decision, FinalizeFailed)
    assert decision.error == "orphan_run"


def test_reconcile_active_spawn_logs_terminal_reason_and_activity_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root, spawn_id = _create_spawn(tmp_path, started_at=_OLD_STARTED_AT)
    record = _get_spawn(state_root, spawn_id)
    logged: dict[str, object] = {}

    monkeypatch.setattr(
        "meridian.lib.state.reaper.is_process_alive",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "meridian.lib.state.reaper.logger.info",
        lambda _message, **kwargs: logged.update(kwargs),
    )

    reconciled = reconcile_active_spawn(state_root, record)

    assert reconciled.status == "failed"
    assert logged["reason"] == "orphan_run"
    assert logged["heartbeat_window_secs"] == 120
    assert logged["recent_activity_artifact"] is None
    assert logged["last_activity_epoch"] is None
    assert logged["inactivity_secs"] is None
