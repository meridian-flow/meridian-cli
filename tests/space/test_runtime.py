
from pathlib import Path

import pytest

from meridian.lib.ops.runtime import SPACE_REQUIRED_ERROR, require_space_id
from meridian.lib.ops.spawn.api import SpawnListInput, spawn_list_sync
from meridian.lib.state.space_store import create_space
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


def test_require_space_id_uses_explicit_value_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    assert require_space_id("s1") == "s1"


def test_require_space_id_raises_without_explicit_or_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    with pytest.raises(ValueError, match=r"ERROR \[SPACE_REQUIRED\]") as exc_info:
        require_space_id(None)

    assert str(exc_info.value) == SPACE_REQUIRED_ERROR


def test_spawn_list_uses_explicit_space_without_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = create_space(tmp_path, name="first")
    second = create_space(tmp_path, name="second")
    first_dir = resolve_space_dir(tmp_path, first.id)
    second_dir = resolve_space_dir(tmp_path, second.id)

    first_run = _start_run(first_dir, prompt="first")
    _start_run(second_dir, prompt="second")

    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)

    result = spawn_list_sync(SpawnListInput(space=first.id, repo_root=tmp_path.as_posix()))

    assert len(result.spawns) == 1
    assert result.spawns[0].spawn_id == first_run
    assert result.spawns[0].space_id == first.id
