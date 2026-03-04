"""Space threading checks for run query and spawn.list operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from meridian.lib.ops._spawn_query import _read_spawn_row
from meridian.lib.ops._runtime import SPACE_REQUIRED_ERROR, require_space_id
from meridian.lib.ops.spawn import (
    SpawnCreateInput,
    SpawnListInput,
    SpawnShowInput,
    SpawnStatsInput,
    SpawnWaitInput,
    spawn_create_sync,
    spawn_list_sync,
    spawn_show_sync,
    spawn_stats_sync,
    spawn_wait_sync,
)
from meridian.lib.space.space_file import create_space
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_space_dir


def _start_run(space_dir: Path, *, prompt: str) -> str:
    spawn_id = spawn_store.start_spawn(
        space_dir,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        prompt=prompt,
    )
    return str(spawn_id)


def test_require_space_id_uses_explicit_value_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    assert require_space_id("s1") == "s1"


def test_require_space_id_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERIDIAN_SPACE_ID", "s-env")

    assert require_space_id(None) == "s-env"


def test_require_space_id_raises_without_explicit_or_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    with pytest.raises(ValueError, match=r"ERROR \[SPACE_REQUIRED\]") as exc_info:
        require_space_id(None)

    assert str(exc_info.value) == SPACE_REQUIRED_ERROR


def test_read_run_row_uses_explicit_space_without_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    space = create_space(tmp_path, name="thread-read")
    space_dir = resolve_space_dir(tmp_path, space.id)
    spawn_id = _start_run(space_dir, prompt="explicit read")
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    row = _read_spawn_row(tmp_path, spawn_id, space.id)

    assert row is not None
    assert row.id == spawn_id


def test_run_create_sync_uses_explicit_space_without_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    space = create_space(tmp_path, name="thread-create")
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    result = spawn_create_sync(
        SpawnCreateInput(
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

    result = spawn_list_sync(SpawnListInput(space=first.id, repo_root=tmp_path.as_posix()))

    assert len(result.spawns) == 1
    assert result.spawns[0].spawn_id == first_run
    assert result.spawns[0].space_id == first.id


def test_run_show_sync_uses_explicit_space_without_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    space = create_space(tmp_path, name="thread-show")
    space_dir = resolve_space_dir(tmp_path, space.id)
    spawn_id = _start_run(space_dir, prompt="show")
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    result = spawn_show_sync(
        SpawnShowInput(spawn_id=spawn_id, space=space.id, repo_root=tmp_path.as_posix())
    )

    assert result.spawn_id == spawn_id
    assert result.space_id == space.id


def test_run_wait_sync_uses_explicit_space_without_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    space = create_space(tmp_path, name="thread-wait")
    space_dir = resolve_space_dir(tmp_path, space.id)
    spawn_id = _start_run(space_dir, prompt="wait")
    spawn_store.finalize_spawn(space_dir, spawn_id, "succeeded", 0, duration_secs=0.1)
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    result = spawn_wait_sync(
        SpawnWaitInput(
            spawn_ids=(spawn_id,),
            space=space.id,
            repo_root=tmp_path.as_posix(),
            timeout_secs=0.1,
            poll_interval_secs=0.01,
        )
    )

    assert result.total_runs == 1
    assert result.spawns[0].spawn_id == spawn_id
    assert result.spawns[0].space_id == space.id


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

    result = spawn_stats_sync(SpawnStatsInput(space=space.id, repo_root=tmp_path.as_posix()))

    assert result.total_runs == 1
    assert result.running == 1
