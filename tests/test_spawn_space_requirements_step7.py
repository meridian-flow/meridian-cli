"""Step 7 run-space requirement behavior checks."""

from __future__ import annotations

import pytest

from meridian.lib.ops._runtime import SPACE_REQUIRED_ERROR
from meridian.lib.ops.spawn import SpawnCreateInput, SpawnListInput, spawn_create_sync, spawn_list_sync
from meridian.lib.space.space_file import list_spaces


def test_spawn_create_requires_space_context_without_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    with pytest.raises(ValueError, match=r"ERROR \[SPACE_REQUIRED\]") as exc_info:
        spawn_create_sync(
            SpawnCreateInput(
                prompt="auto-create",
                model="gpt-5.3-codex",
                dry_run=True,
                repo_root=tmp_path.as_posix(),
            )
        )

    assert str(exc_info.value) == SPACE_REQUIRED_ERROR
    assert len(list_spaces(tmp_path)) == 0


def test_non_spawn_commands_require_space_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    with pytest.raises(ValueError, match=r"ERROR \[SPACE_REQUIRED\]") as exc_info:
        spawn_list_sync(SpawnListInput(repo_root=tmp_path.as_posix()))

    assert str(exc_info.value) == SPACE_REQUIRED_ERROR
