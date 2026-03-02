"""CLI spawn.* plumbing tests consolidated in one module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meridian.cli import spawn as run_cli
from meridian.lib.ops.spawn import (
    SpawnActionOutput,
    SpawnCreateInput,
    SpawnDetailOutput,
    SpawnShowInput,
    SpawnStatsInput,
    SpawnStatsOutput,
    SpawnWaitInput,
    SpawnWaitMultiOutput,
)
from meridian.lib.space.space_file import create_space


def _detail(
    spawn_id: str = "r1",
    *,
    status: str = "succeeded",
    exit_code: int | None = 0,
    space_id: str | None = "s1",
) -> SpawnDetailOutput:
    return SpawnDetailOutput(
        spawn_id=spawn_id,
        status=status,
        model="gpt-5.3-codex",
        harness="codex",
        space_id=space_id,
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
    exit = run_tuple[0].exit_code if len(run_tuple) == 1 else None
    return SpawnWaitMultiOutput(
        spawns=run_tuple,
        total_runs=len(run_tuple),
        succeeded_runs=succeeded_runs,
        failed_runs=failed_runs,
        cancelled_runs=cancelled_runs,
        any_failed=any_failed,
        spawn_id=spawn_id,
        status=status,
        exit_code=exit,
    )


@pytest.mark.parametrize(
    ("kwargs", "assertions"),
    [
        pytest.param(
            {"verbose": True, "quiet": True, "dry_run": True},
            {"verbose": True, "quiet": True, "stream": False, "background": False},
            id="verbose-quiet",
        ),
        pytest.param(
            {"stream": True, "dry_run": True},
            {"verbose": False, "quiet": False, "stream": True, "background": False},
            id="stream",
        ),
        pytest.param(
            {"background": True},
            {"background": True},
            id="background",
        ),
    ],
)
def test_spawn_create_passes_flags(monkeypatch: pytest.MonkeyPatch, kwargs: dict, assertions: dict) -> None:
    captured: dict[str, SpawnCreateInput] = {}
    emitted: list[SpawnActionOutput] = []

    def fake_spawn_create_sync(payload: SpawnCreateInput) -> SpawnActionOutput:
        captured["payload"] = payload
        status = "running" if payload.background else "dry-run"
        return SpawnActionOutput(command="spawn.create", status=status, spawn_id="r1")

    monkeypatch.setattr(run_cli, "spawn_create_sync", fake_spawn_create_sync)
    run_cli._spawn_create(emitted.append, prompt="test", **kwargs)

    payload = captured["payload"]
    for key, value in assertions.items():
        assert getattr(payload, key) is value
    assert emitted[0].status in {"dry-run", "running"}


@pytest.mark.parametrize(
    ("result", "expected_exit"),
    [
        pytest.param(SpawnActionOutput(command="spawn.create", status="failed", exit_code=7), 7, id="with-exit"),
        pytest.param(SpawnActionOutput(command="spawn.create", status="failed"), 1, id="default-exit"),
    ],
)
def test_spawn_create_failed_results_raise_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
    result: SpawnActionOutput,
    expected_exit: int,
) -> None:
    monkeypatch.setattr(run_cli, "spawn_create_sync", lambda payload: result)

    with pytest.raises(SystemExit) as exc_info:
        run_cli._spawn_create(lambda _: None, prompt="test")

    assert int(exc_info.value.code) == expected_exit


def test_spawn_show_passes_report_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, SpawnShowInput] = {}
    emitted: list[SpawnDetailOutput] = []

    def fake_spawn_show_sync(payload: SpawnShowInput) -> SpawnDetailOutput:
        captured["payload"] = payload
        return _detail()

    monkeypatch.setattr(run_cli, "spawn_show_sync", fake_spawn_show_sync)
    run_cli._spawn_show(emitted.append, spawn_id="r1", report=True)

    assert captured["payload"].report is True
    assert emitted[0].spawn_id == "r1"


def test_spawn_stats_passes_session_and_space_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, SpawnStatsInput] = {}
    emitted: list[SpawnStatsOutput] = []

    def fake_spawn_stats_sync(payload: SpawnStatsInput) -> SpawnStatsOutput:
        captured["payload"] = payload
        return SpawnStatsOutput(
            total_runs=1,
            succeeded=1,
            failed=0,
            cancelled=0,
            running=0,
            total_duration_secs=2.0,
            total_cost_usd=0.1,
            models={"gpt-5.3-codex": 1},
        )

    monkeypatch.setattr(run_cli, "spawn_stats_sync", fake_spawn_stats_sync)
    run_cli._spawn_stats(emitted.append, session="sess-1", space="s1")

    assert captured["payload"] == SpawnStatsInput(session="sess-1", space="s1")
    assert emitted[0].total_runs == 1
    assert emitted[0].models == {"gpt-5.3-codex": 1}


def test_cli_spawn_stats_json_output(
    run_meridian,
    cli_env: dict[str, str],
    tmp_path: Path,
) -> None:
    cli_env["MERIDIAN_REPO_ROOT"] = tmp_path.as_posix()
    space = create_space(tmp_path, name="cli-stats")
    cli_env["MERIDIAN_SPACE_ID"] = space.id

    result = run_meridian(["--json", "spawn", "stats"])
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["total_runs"] >= 0
    assert "models" in payload


def test_spawn_wait_passes_multiple_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, SpawnWaitInput] = {}
    emitted: list[SpawnWaitMultiOutput] = []

    def fake_spawn_wait_sync(payload: SpawnWaitInput) -> SpawnWaitMultiOutput:
        captured["payload"] = payload
        return _wait_output(_detail("r1"), _detail("r2"))

    monkeypatch.setattr(run_cli, "spawn_wait_sync", fake_spawn_wait_sync)
    run_cli._spawn_wait(emitted.append, spawn_ids=("r1", "r2"), timeout_secs=30.0)

    assert captured["payload"].spawn_ids == ("r1", "r2")
    assert emitted[0].total_runs == 2
    assert emitted[0].any_failed is False


def test_spawn_wait_exits_nonzero_when_any_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        run_cli,
        "spawn_wait_sync",
        lambda payload: _wait_output(_detail("r1"), _detail("r2", status="failed", exit_code=1)),
    )

    with pytest.raises(SystemExit) as exc_info:
        run_cli._spawn_wait(lambda _: None, spawn_ids=("r1", "r2"))

    assert int(exc_info.value.code) == 1


def test_spawn_wait_passes_report_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, SpawnWaitInput] = {}
    emitted: list[SpawnWaitMultiOutput] = []

    def fake_spawn_wait_sync(payload: SpawnWaitInput) -> SpawnWaitMultiOutput:
        captured["payload"] = payload
        return _wait_output(_detail("r1"))

    monkeypatch.setattr(run_cli, "spawn_wait_sync", fake_spawn_wait_sync)
    run_cli._spawn_wait(emitted.append, spawn_ids=("r1",), report=True)

    assert captured["payload"].report is True
    assert emitted[0].spawn_id == "r1"
