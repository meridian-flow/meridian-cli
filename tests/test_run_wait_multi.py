"""run.wait multi-run polling and compatibility tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from meridian.lib.ops import run as run_ops
from meridian.lib.ops.run import RunDetailOutput, RunWaitInput


def _detail_from_status(
    run_id: str,
    status: str,
    duration_secs: float | None,
    exit_code: int | None,
) -> RunDetailOutput:
    return RunDetailOutput(
        run_id=run_id,
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
        skills=(),
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

    def fake_read_run_row(_: Path, run_id: str) -> SimpleNamespace:
        sequence = rows_by_id[run_id]
        if len(sequence) > 1:
            return sequence.pop(0)
        return sequence[0]

    monkeypatch.setattr(run_ops, "_read_run_row", fake_read_run_row)
    monkeypatch.setattr(
        run_ops,
        "_detail_from_row",
        lambda repo_root, row, report, include_files: _detail_from_status(
            run_id=str(row.id),
            status=str(row.status),
            duration_secs=cast("float | None", row.duration_secs),
            exit_code=cast("int | None", row.exit_code),
        ),
    )

    result = run_ops.run_wait_sync(
        RunWaitInput(
            run_ids=("r1", "r2"),
            timeout_secs=5.0,
            poll_interval_secs=0.0,
        )
    )

    assert [run.run_id for run in result.runs] == ["r1", "r2"]
    assert [run.status for run in result.runs] == ["succeeded", "failed"]
    assert result.total_runs == 2
    assert result.succeeded_runs == 1
    assert result.failed_runs == 1
    assert result.cancelled_runs == 0
    assert result.any_failed is True
    assert result.run_id is None
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
        "_read_run_row",
        lambda _repo_root, run_id: SimpleNamespace(
            id=run_id, status="running", duration_secs=None, exit_code=None
        ),
    )

    with pytest.raises(TimeoutError, match="Timed out waiting for run\\(s\\)"):
        run_ops.run_wait_sync(
            RunWaitInput(
                run_ids=("r1", "r2"),
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
        "_read_run_row",
        lambda _repo_root, run_id: SimpleNamespace(
            id=run_id, status="succeeded", duration_secs=1.0, exit_code=0
        ),
    )
    monkeypatch.setattr(
        run_ops,
        "_detail_from_row",
        lambda repo_root, row, report, include_files: _detail_from_status(
            run_id=str(row.id),
            status=str(row.status),
            duration_secs=cast("float | None", row.duration_secs),
            exit_code=cast("int | None", row.exit_code),
        ),
    )

    result = run_ops.run_wait_sync(RunWaitInput(run_id="legacy-run"))
    assert result.total_runs == 1
    assert result.run_id == "legacy-run"
    assert result.status == "succeeded"
    assert result.exit_code == 0
