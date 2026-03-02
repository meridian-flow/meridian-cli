"""CLI plumbing and exit behavior for multi-run spawn.wait."""

from __future__ import annotations

import pytest

from meridian.cli import spawn as run_cli
from meridian.lib.ops.spawn import SpawnDetailOutput, SpawnWaitInput, SpawnWaitMultiOutput


def _detail(spawn_id: str, status: str, exit_code: int | None) -> SpawnDetailOutput:
    return SpawnDetailOutput(
        spawn_id=spawn_id,
        status=status,
        model="gpt-5.3-codex",
        harness="codex",
        space_id=None,
        started_at="2026-02-27T00:00:00Z",
        finished_at="2026-02-27T00:00:01Z",
        duration_secs=1.0,
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


def _wait_output(*spawns: SpawnDetailOutput) -> SpawnWaitMultiOutput:
    run_tuple = tuple(spawns)
    succeeded_runs = sum(1 for run in run_tuple if run.status == "succeeded")
    failed_runs = sum(1 for run in run_tuple if run.status == "failed")
    cancelled_runs = sum(1 for run in run_tuple if run.status == "cancelled")
    any_failed = any(run.status in {"failed", "cancelled"} for run in run_tuple)
    spawn_id = run_tuple[0].spawn_id if len(run_tuple) == 1 else None
    status = run_tuple[0].status if len(run_tuple) == 1 else None
    exit_code = run_tuple[0].exit_code if len(run_tuple) == 1 else None
    return SpawnWaitMultiOutput(
        spawns=run_tuple,
        total_runs=len(run_tuple),
        succeeded_runs=succeeded_runs,
        failed_runs=failed_runs,
        cancelled_runs=cancelled_runs,
        any_failed=any_failed,
        spawn_id=spawn_id,
        status=status,
        exit_code=exit_code,
    )


def test_run_wait_passes_multiple_run_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, SpawnWaitInput] = {}
    emitted: list[SpawnWaitMultiOutput] = []

    def fake_run_wait_sync(payload: SpawnWaitInput) -> SpawnWaitMultiOutput:
        captured["payload"] = payload
        return _wait_output(_detail("r1", "succeeded", 0), _detail("r2", "succeeded", 0))

    monkeypatch.setattr(run_cli, "spawn_wait_sync", fake_run_wait_sync)

    run_cli._spawn_wait(
        emitted.append,
        spawn_ids=("r1", "r2"),
        timeout_secs=30.0,
    )

    assert captured["payload"].spawn_ids == ("r1", "r2")
    assert emitted[0].total_runs == 2
    assert emitted[0].any_failed is False


def test_run_wait_exits_nonzero_when_any_run_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        run_cli,
        "spawn_wait_sync",
        lambda payload: _wait_output(_detail("r1", "succeeded", 0), _detail("r2", "failed", 1)),
    )

    with pytest.raises(SystemExit) as exc_info:
        run_cli._spawn_wait(
            lambda _: None,
            spawn_ids=("r1", "r2"),
        )

    assert int(exc_info.value.code) == 1


def test_run_wait_passes_report_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, SpawnWaitInput] = {}
    emitted: list[SpawnWaitMultiOutput] = []

    def fake_run_wait_sync(payload: SpawnWaitInput) -> SpawnWaitMultiOutput:
        captured["payload"] = payload
        return _wait_output(_detail("r1", "succeeded", 0))

    monkeypatch.setattr(run_cli, "spawn_wait_sync", fake_run_wait_sync)

    run_cli._spawn_wait(
        emitted.append,
        spawn_ids=("r1",),
        report=True,
    )

    assert captured["payload"].report is True
    assert emitted[0].spawn_id == "r1"
