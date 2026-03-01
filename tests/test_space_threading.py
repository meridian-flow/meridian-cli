"""Space threading checks for run query and run.list operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from meridian.lib.ops._run_query import _read_run_row, _resolve_space_id
from meridian.lib.ops._runtime import SPACE_REQUIRED_ERROR
from meridian.lib.ops.run import (
    RunCreateInput,
    RunListInput,
    RunShowInput,
    RunStatsInput,
    RunWaitInput,
    run_create_sync,
    run_list_sync,
    run_show_sync,
    run_stats_sync,
    run_wait_sync,
)
from meridian.lib.space.space_file import create_space
from meridian.lib.state import run_store
from meridian.lib.state.paths import resolve_space_dir


def _start_run(space_dir: Path, *, prompt: str) -> str:
    run_id = run_store.start_run(
        space_dir,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        prompt=prompt,
    )
    return str(run_id)


def test_resolve_space_id_uses_explicit_value_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    assert _resolve_space_id("s1") == "s1"


def test_resolve_space_id_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERIDIAN_SPACE_ID", "s-env")

    assert _resolve_space_id(None) == "s-env"


def test_resolve_space_id_raises_without_explicit_or_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    with pytest.raises(ValueError, match=r"ERROR \[SPACE_REQUIRED\]") as exc_info:
        _resolve_space_id(None)

    assert str(exc_info.value) == SPACE_REQUIRED_ERROR


def test_read_run_row_uses_explicit_space_without_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    space = create_space(tmp_path, name="thread-read")
    space_dir = resolve_space_dir(tmp_path, space.id)
    run_id = _start_run(space_dir, prompt="explicit read")
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    row = _read_run_row(tmp_path, run_id, space.id)

    assert row is not None
    assert row.id == run_id


def test_run_create_sync_uses_explicit_space_without_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    space = create_space(tmp_path, name="thread-create")
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    result = run_create_sync(
        RunCreateInput(
            prompt="test",
            model="gpt-5.3-codex",
            dry_run=True,
            space=space.id,
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.status == "dry-run"
    assert result.warning is None or "WARNING [SPACE_AUTO_CREATED]" not in result.warning


def test_run_list_sync_uses_payload_space_without_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = create_space(tmp_path, name="first")
    second = create_space(tmp_path, name="second")
    first_dir = resolve_space_dir(tmp_path, first.id)
    second_dir = resolve_space_dir(tmp_path, second.id)

    first_run = _start_run(first_dir, prompt="first")
    _ = _start_run(second_dir, prompt="second")

    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    result = run_list_sync(RunListInput(space=first.id, repo_root=tmp_path.as_posix()))

    assert len(result.runs) == 1
    assert result.runs[0].run_id == first_run
    assert result.runs[0].space_id == first.id


def test_run_show_sync_uses_explicit_space_without_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    space = create_space(tmp_path, name="thread-show")
    space_dir = resolve_space_dir(tmp_path, space.id)
    run_id = _start_run(space_dir, prompt="show")
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    result = run_show_sync(
        RunShowInput(run_id=run_id, space=space.id, repo_root=tmp_path.as_posix())
    )

    assert result.run_id == run_id
    assert result.space_id == space.id


def test_run_wait_sync_uses_explicit_space_without_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    space = create_space(tmp_path, name="thread-wait")
    space_dir = resolve_space_dir(tmp_path, space.id)
    run_id = _start_run(space_dir, prompt="wait")
    run_store.finalize_run(space_dir, run_id, "succeeded", 0, duration_secs=0.1)
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    result = run_wait_sync(
        RunWaitInput(
            run_ids=(run_id,),
            space=space.id,
            repo_root=tmp_path.as_posix(),
            timeout_secs=0.1,
            poll_interval_secs=0.01,
        )
    )

    assert result.total_runs == 1
    assert result.runs[0].run_id == run_id
    assert result.runs[0].space_id == space.id


def test_run_stats_sync_uses_explicit_space_without_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    space = create_space(tmp_path, name="thread-stats")
    other_space = create_space(tmp_path, name="thread-stats-other")
    space_dir = resolve_space_dir(tmp_path, space.id)
    other_space_dir = resolve_space_dir(tmp_path, other_space.id)
    _start_run(space_dir, prompt="stats-included")
    _start_run(other_space_dir, prompt="stats-excluded")
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    result = run_stats_sync(RunStatsInput(space=space.id, repo_root=tmp_path.as_posix()))

    assert result.total_runs == 1
    assert result.running == 1
