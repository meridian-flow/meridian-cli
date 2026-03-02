"""spawn.wait multi-run polling and compatibility tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from meridian.lib.ops import spawn as run_ops
from meridian.lib.ops.spawn import SpawnDetailOutput, SpawnWaitInput


def _detail_from_status(
    spawn_id: str,
    status: str,
    duration_secs: float | None,
    exit_code: int | None,
) -> SpawnDetailOutput:
    return SpawnDetailOutput(
        spawn_id=spawn_id,
        status=status,
        model="gpt-5.3-codex",
        harness="codex",
        space_id=None,
        started_at="2026-02-27T00:00:00Z",
        finished_at="2026-02-27T00:00:01Z",
        duration_secs=duration_secs,
        exit_code=exit_code,
        failure_reason=None,
        input_tokens=None,
        output_tokens=None,
        cost_usd=None,
        report_path=None,
        report_summary=None,
        report=None,
        files_touched=None,
    )


def test_run_wait_sync_waits_for_all_runs_and_returns_ordered_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        run_ops,
        "resolve_runtime_root_and_config",
        lambda _: (Path("/tmp/repo"), SimpleNamespace(wait_timeout_seconds=30.0, retry_backoff_seconds=0.0)),
    )
    monkeypatch.setattr(run_ops.time, "sleep", lambda _: None)

    rows_by_id: dict[str, list[SimpleNamespace]] = {
        "r1": [
            SimpleNamespace(id="r1", status="running", duration_secs=None, exit_code=None),
            SimpleNamespace(id="r1", status="succeeded", duration_secs=3.2, exit_code=0),
        ],
        "r2": [
            SimpleNamespace(id="r2", status="queued", duration_secs=None, exit_code=None),
            SimpleNamespace(id="r2", status="failed", duration_secs=4.5, exit_code=1),
        ],
    }

    def fake_read_run_row(_: Path, spawn_id: str, _space: str | None = None) -> SimpleNamespace:
        sequence = rows_by_id[spawn_id]
        if len(sequence) > 1:
            return sequence.pop(0)
        return sequence[0]

    monkeypatch.setattr(run_ops, "_read_spawn_row", fake_read_run_row)
    monkeypatch.setattr(
        run_ops,
        "_detail_from_row",
        lambda repo_root, row, report, include_files, space_id=None: _detail_from_status(
            spawn_id=str(row.id),
            status=str(row.status),
            duration_secs=cast("float | None", row.duration_secs),
            exit_code=cast("int | None", row.exit_code),
        ),
    )

    result = run_ops.spawn_wait_sync(
        SpawnWaitInput(
            spawn_ids=("r1", "r2"),
            timeout_secs=5.0,
            poll_interval_secs=0.0,
        )
    )

    assert [run.spawn_id for run in result.spawns] == ["r1", "r2"]
    assert [run.status for run in result.spawns] == ["succeeded", "failed"]
    assert result.total_runs == 2
    assert result.succeeded_runs == 1
    assert result.failed_runs == 1
    assert result.cancelled_runs == 0
    assert result.any_failed is True
    assert result.spawn_id is None
    assert result.status is None
    assert result.exit_code is None


def test_run_wait_sync_timeout_is_global_across_all_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        run_ops,
        "resolve_runtime_root_and_config",
        lambda _: (Path("/tmp/repo"), SimpleNamespace(wait_timeout_seconds=1.0, retry_backoff_seconds=0.1)),
    )
    monkeypatch.setattr(run_ops.time, "sleep", lambda _: None)

    clock = {"value": 0.0}

    def fake_monotonic() -> float:
        current = clock["value"]
        clock["value"] += 0.4
        return current

    monkeypatch.setattr(run_ops.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(
        run_ops,
        "_read_spawn_row",
        lambda _repo_root, spawn_id, _space=None: SimpleNamespace(
            id=spawn_id, status="running", duration_secs=None, exit_code=None
        ),
    )

    with pytest.raises(TimeoutError, match="Timed out waiting for spawn\\(s\\)"):
        run_ops.spawn_wait_sync(
            SpawnWaitInput(
                spawn_ids=("r1", "r2"),
                timeout_secs=1.0,
                poll_interval_secs=0.1,
            )
        )


def test_run_wait_sync_accepts_legacy_run_id_alias_for_single_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        run_ops,
        "resolve_runtime_root_and_config",
        lambda _: (Path("/tmp/repo"), SimpleNamespace(wait_timeout_seconds=5.0, retry_backoff_seconds=0.1)),
    )
    monkeypatch.setattr(
        run_ops,
        "_read_spawn_row",
        lambda _repo_root, spawn_id, _space=None: SimpleNamespace(
            id=spawn_id, status="succeeded", duration_secs=1.0, exit_code=0
        ),
    )
    monkeypatch.setattr(
        run_ops,
        "_detail_from_row",
        lambda repo_root, row, report, include_files, space_id=None: _detail_from_status(
            spawn_id=str(row.id),
            status=str(row.status),
            duration_secs=cast("float | None", row.duration_secs),
            exit_code=cast("int | None", row.exit_code),
        ),
    )

    result = run_ops.spawn_wait_sync(SpawnWaitInput(spawn_id="legacy-run"))
    assert result.total_runs == 1
    assert result.spawn_id == "legacy-run"
    assert result.status == "succeeded"
    assert result.exit_code == 0


def test_run_wait_sync_emits_heartbeat_with_default_verbosity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        run_ops,
        "resolve_runtime_root_and_config",
        lambda _: (
            Path("/tmp/repo"),
            SimpleNamespace(
                wait_timeout_seconds=5.0,
                retry_backoff_seconds=0.1,
                output=SimpleNamespace(verbosity="normal"),
            ),
        ),
    )
    monkeypatch.setattr(run_ops.time, "sleep", lambda _: None)
    monkeypatch.setattr(run_ops, "_WAIT_HEARTBEAT_INTERVAL_SECS", 0.0)

    clock = {"value": 0.0}

    def fake_monotonic() -> float:
        current = clock["value"]
        clock["value"] += 0.11
        return current

    monkeypatch.setattr(run_ops.time, "monotonic", fake_monotonic)

    rows = [
        SimpleNamespace(id="r1", status="running", duration_secs=None, exit_code=None),
        SimpleNamespace(id="r1", status="succeeded", duration_secs=1.0, exit_code=0),
    ]
    monkeypatch.setattr(
        run_ops,
        "_read_spawn_row",
        lambda _repo_root, _spawn_id, _space=None: rows.pop(0) if len(rows) > 1 else rows[0],
    )
    monkeypatch.setattr(
        run_ops,
        "_detail_from_row",
        lambda repo_root, row, report, include_files, space_id=None: _detail_from_status(
            spawn_id=str(row.id),
            status=str(row.status),
            duration_secs=cast("float | None", row.duration_secs),
            exit_code=cast("int | None", row.exit_code),
        ),
    )

    heartbeats: list[str] = []
    monkeypatch.setattr(run_ops, "_emit_wait_heartbeat", heartbeats.append)

    result = run_ops.spawn_wait_sync(
        SpawnWaitInput(
            spawn_ids=("r1",),
            timeout_secs=5.0,
            poll_interval_secs=0.1,
        )
    )

    assert result.status == "succeeded"
    assert heartbeats == ["waiting for 1 spawn(s) to finish..."]


def test_run_wait_sync_suppresses_heartbeat_when_quiet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        run_ops,
        "resolve_runtime_root_and_config",
        lambda _: (
            Path("/tmp/repo"),
            SimpleNamespace(
                wait_timeout_seconds=5.0,
                retry_backoff_seconds=0.1,
                output=SimpleNamespace(verbosity="verbose"),
            ),
        ),
    )
    monkeypatch.setattr(run_ops.time, "sleep", lambda _: None)
    monkeypatch.setattr(run_ops, "_WAIT_HEARTBEAT_INTERVAL_SECS", 0.0)

    clock = {"value": 0.0}

    def fake_monotonic() -> float:
        current = clock["value"]
        clock["value"] += 0.11
        return current

    monkeypatch.setattr(run_ops.time, "monotonic", fake_monotonic)

    rows = [
        SimpleNamespace(id="r1", status="running", duration_secs=None, exit_code=None),
        SimpleNamespace(id="r1", status="succeeded", duration_secs=1.0, exit_code=0),
    ]
    monkeypatch.setattr(
        run_ops,
        "_read_spawn_row",
        lambda _repo_root, _spawn_id, _space=None: rows.pop(0) if len(rows) > 1 else rows[0],
    )
    monkeypatch.setattr(
        run_ops,
        "_detail_from_row",
        lambda repo_root, row, report, include_files, space_id=None: _detail_from_status(
            spawn_id=str(row.id),
            status=str(row.status),
            duration_secs=cast("float | None", row.duration_secs),
            exit_code=cast("int | None", row.exit_code),
        ),
    )

    heartbeats: list[str] = []
    monkeypatch.setattr(run_ops, "_emit_wait_heartbeat", heartbeats.append)

    result = run_ops.spawn_wait_sync(
        SpawnWaitInput(
            spawn_ids=("r1",),
            timeout_secs=5.0,
            poll_interval_secs=0.1,
            quiet=True,
        )
    )

    assert result.status == "succeeded"
    assert heartbeats == []


def test_render_wait_heartbeat_verbose_lists_pending_spawns() -> None:
    rendered = run_ops._render_wait_heartbeat(
        {"s3", "s1", "s2"},
        elapsed_secs=12.3,
        mode="verbose",
    )
    assert rendered == "waiting 12.3s; pending spawns (3): s1, s2, s3"
