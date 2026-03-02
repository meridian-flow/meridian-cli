"""Spawn reference resolution tests for @latest/@last-failed/@last-completed."""

from __future__ import annotations

from pathlib import Path

import pytest

import meridian.lib.ops.spawn as run_ops
from meridian.lib.ops._spawn_query import resolve_spawn_reference
from meridian.lib.ops.spawn import (
    SpawnActionOutput,
    SpawnContinueInput,
    SpawnShowInput,
    SpawnWaitInput,
)
from meridian.lib.space.space_file import create_space
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_space_dir


def _create_run(space_dir: Path, *, prompt: str, status: str) -> str:
    spawn_id = spawn_store.start_spawn(
        space_dir,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        prompt=prompt,
    )
    if status != "running":
        exit_code = 0 if status == "succeeded" else 1
        spawn_store.finalize_spawn(space_dir, spawn_id, status, exit_code)
    return str(spawn_id)


def test_resolve_run_reference_selectors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    space = create_space(tmp_path, name="refs")
    space_dir = resolve_space_dir(tmp_path, space.id)
    monkeypatch.setenv("MERIDIAN_SPACE_ID", space.id)

    run1 = _create_run(space_dir, prompt="first", status="succeeded")
    run2 = _create_run(space_dir, prompt="second", status="failed")
    run3 = _create_run(space_dir, prompt="third", status="succeeded")

    assert resolve_spawn_reference(tmp_path, "@latest") == run3
    assert resolve_spawn_reference(tmp_path, "@last-failed") == run2
    assert resolve_spawn_reference(tmp_path, "@last-completed") == run3
    assert resolve_spawn_reference(tmp_path, run1) == run1


def test_resolve_run_reference_raises_for_empty_unknown_or_missing_selector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space = create_space(tmp_path, name="refs")
    space_dir = resolve_space_dir(tmp_path, space.id)
    monkeypatch.setenv("MERIDIAN_SPACE_ID", space.id)

    _ = _create_run(space_dir, prompt="only", status="succeeded")

    with pytest.raises(ValueError, match="spawn_id is required"):
        resolve_spawn_reference(tmp_path, "   ")

    with pytest.raises(ValueError, match="Unknown spawn reference '@nope'"):
        resolve_spawn_reference(tmp_path, "@nope")

    with pytest.raises(ValueError, match="No spawns found for reference '@last-failed'"):
        resolve_spawn_reference(tmp_path, "@last-failed")


def test_run_show_and_wait_accept_run_references(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space = create_space(tmp_path, name="refs")
    space_dir = resolve_space_dir(tmp_path, space.id)
    monkeypatch.setenv("MERIDIAN_SPACE_ID", space.id)

    run1 = _create_run(space_dir, prompt="ok", status="succeeded")
    run2 = _create_run(space_dir, prompt="broken", status="failed")

    shown_latest = run_ops.spawn_show_sync(
        SpawnShowInput(spawn_id="@latest", repo_root=tmp_path.as_posix())
    )
    shown_failed = run_ops.spawn_show_sync(
        SpawnShowInput(spawn_id="@last-failed", repo_root=tmp_path.as_posix())
    )
    waited = run_ops.spawn_wait_sync(
        SpawnWaitInput(spawn_ids=("@latest",), repo_root=tmp_path.as_posix(), poll_interval_secs=0.0)
    )

    assert shown_latest.spawn_id == run2
    assert shown_failed.spawn_id == run2
    assert waited.spawn_id == run2
    assert waited.status == "failed"
    assert run1 != run2


def test_run_continue_and_retry_accept_latest_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space = create_space(tmp_path, name="refs")
    space_dir = resolve_space_dir(tmp_path, space.id)
    monkeypatch.setenv("MERIDIAN_SPACE_ID", space.id)

    spawn_id = _create_run(space_dir, prompt="stored prompt", status="succeeded")

    captured_payloads: list[object] = []

    def fake_run_create_sync(payload: object) -> SpawnActionOutput:
        captured_payloads.append(payload)
        return SpawnActionOutput(
            command="spawn.create",
            status="succeeded",
            spawn_id=f"r-next-{len(captured_payloads)}",
        )

    monkeypatch.setattr(run_ops, "spawn_create_sync", fake_run_create_sync)

    continued = run_ops.spawn_continue_sync(
        SpawnContinueInput(spawn_id="@latest", prompt="", repo_root=tmp_path.as_posix())
    )

    assert continued.command == "spawn.continue"
    assert len(captured_payloads) == 1
    assert getattr(captured_payloads[0], "prompt") == "stored prompt"
    assert resolve_spawn_reference(tmp_path, "@latest") == spawn_id
