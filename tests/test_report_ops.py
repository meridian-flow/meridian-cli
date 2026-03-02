"""report.* operation behavior and spawn-reference resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from meridian.lib.ops.report import (
    ReportCreateInput,
    ReportSearchInput,
    ReportShowInput,
    report_create_sync,
    report_search_sync,
    report_show_sync,
)
from meridian.lib.space.space_file import create_space
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_space_dir


def _create_spawn(space_dir: Path, *, prompt: str, status: str) -> str:
    spawn_id = spawn_store.start_spawn(
        space_dir,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        prompt=prompt,
    )
    if status != "running":
        spawn_store.finalize_spawn(
            space_dir,
            spawn_id,
            status,
            0 if status == "succeeded" else 1,
        )
    return str(spawn_id)


def test_report_create_and_show_default_to_current_spawn_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space = create_space(tmp_path, name="report")
    space_dir = resolve_space_dir(tmp_path, space.id)
    spawn_id = _create_spawn(space_dir, prompt="first", status="succeeded")
    monkeypatch.setenv("MERIDIAN_SPACE_ID", space.id)
    monkeypatch.setenv("MERIDIAN_SPAWN_ID", spawn_id)

    created = report_create_sync(
        ReportCreateInput(
            content="# Report\n\ndone",
            repo_root=tmp_path.as_posix(),
        )
    )
    shown = report_show_sync(
        ReportShowInput(
            repo_root=tmp_path.as_posix(),
        )
    )

    assert created.spawn_id == spawn_id
    assert shown.spawn_id == spawn_id
    assert "done" in shown.report
    assert Path(created.report_path).is_file()


def test_report_show_and_search_support_spawn_references(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space = create_space(tmp_path, name="report-refs")
    space_dir = resolve_space_dir(tmp_path, space.id)
    _ = _create_spawn(space_dir, prompt="old", status="succeeded")
    latest = _create_spawn(space_dir, prompt="new", status="succeeded")
    monkeypatch.setenv("MERIDIAN_SPACE_ID", space.id)

    report_create_sync(
        ReportCreateInput(
            content="alpha report text",
            spawn_id=latest,
            repo_root=tmp_path.as_posix(),
        )
    )

    shown = report_show_sync(
        ReportShowInput(
            spawn_id="@latest",
            repo_root=tmp_path.as_posix(),
        )
    )
    searched = report_search_sync(
        ReportSearchInput(
            query="alpha",
            spawn_id="@latest",
            repo_root=tmp_path.as_posix(),
        )
    )

    assert shown.spawn_id == latest
    assert "alpha report text" in shown.report
    assert len(searched.results) == 1
    assert searched.results[0].spawn_id == latest
