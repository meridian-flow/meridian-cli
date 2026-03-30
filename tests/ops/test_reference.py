from pathlib import Path

import pytest

from meridian.lib.ops import reference
from meridian.lib.ops.reference import resolve_session_reference
from meridian.lib.state import session_store, spawn_store
from meridian.lib.state.paths import resolve_state_paths


def _state_root(repo_root: Path) -> Path:
    state_root = resolve_state_paths(repo_root).root_dir
    state_root.mkdir(parents=True, exist_ok=True)
    return state_root


def _seed_session(
    state_root: Path,
    *,
    chat_id: str,
    harness_session_id: str,
    extra_harness_session_ids: tuple[str, ...] = (),
    work_id: str | None = None,
) -> str:
    resolved_chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id=harness_session_id,
        model="gpt-5.4",
        chat_id=chat_id,
        agent="coder",
        skills=("skill-a", "skill-b"),
    )
    if work_id is not None:
        session_store.update_session_work_id(state_root, resolved_chat_id, work_id)
    for candidate in extra_harness_session_ids:
        session_store.update_session_harness_id(state_root, resolved_chat_id, candidate)
    session_store.stop_session(state_root, resolved_chat_id)
    return resolved_chat_id


def _seed_spawn(
    state_root: Path,
    *,
    spawn_id: str,
    chat_id: str,
    harness_session_id: str | None,
) -> None:
    spawn_store.start_spawn(
        state_root,
        spawn_id=spawn_id,
        chat_id=chat_id,
        model="gpt-5.3-codex",
        agent="coder",
        skills=("skill-c",),
        harness="codex",
        prompt="seed prompt",
        work_id="w-spawn",
        harness_session_id=harness_session_id,
    )


def test_resolve_session_reference_uses_latest_chat_session_id(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_root = _state_root(repo_root)
    chat_id = _seed_session(
        state_root,
        chat_id="c41",
        harness_session_id="session-1",
        extra_harness_session_ids=("session-2", "session-3"),
        work_id="w-chat",
    )

    resolved = resolve_session_reference(repo_root, chat_id)

    assert resolved.harness_session_id == "session-3"
    assert resolved.harness == "codex"
    assert resolved.source_chat_id == "c41"
    assert resolved.source_model == "gpt-5.4"
    assert resolved.source_agent == "coder"
    assert resolved.source_skills == ("skill-a", "skill-b")
    assert resolved.source_work_id == "w-chat"
    assert resolved.tracked is True
    assert resolved.warning is None


def test_resolve_session_reference_for_spawn_id_reads_spawn_metadata(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_root = _state_root(repo_root)
    _seed_spawn(state_root, spawn_id="p7", chat_id="c7", harness_session_id="spawn-session-7")

    resolved = resolve_session_reference(repo_root, "p7")

    assert resolved.harness_session_id == "spawn-session-7"
    assert resolved.harness == "codex"
    assert resolved.source_chat_id == "c7"
    assert resolved.source_model == "gpt-5.3-codex"
    assert resolved.source_agent == "coder"
    assert resolved.source_skills == ("skill-c",)
    assert resolved.source_work_id == "w-spawn"
    assert resolved.tracked is True
    assert resolved.warning is None


def test_resolve_session_reference_allows_spawn_without_harness_session_id(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_root = _state_root(repo_root)
    _seed_spawn(state_root, spawn_id="p8", chat_id="c8", harness_session_id=None)

    resolved = resolve_session_reference(repo_root, "p8")

    assert resolved.harness_session_id is None
    assert resolved.harness == "codex"
    assert resolved.tracked is True
    assert resolved.missing_harness_session_id is True


def test_resolve_session_reference_falls_back_to_untracked_raw_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    monkeypatch.setattr(
        reference,
        "infer_harness_from_untracked_session_ref",
        lambda *_args, **_kwargs: "claude",
    )

    resolved = resolve_session_reference(repo_root, "raw-session-id")

    assert resolved.harness_session_id == "raw-session-id"
    assert resolved.harness == "claude"
    assert resolved.source_chat_id is None
    assert resolved.source_model is None
    assert resolved.source_agent is None
    assert resolved.source_skills == ()
    assert resolved.source_work_id is None
    assert resolved.tracked is False
    assert resolved.missing_harness_session_id is False
    assert (
        resolved.warning
        == "Session 'raw-session-id' is not tracked yet; "
        "resuming with the provided harness session id."
    )


def test_resolve_session_reference_missing_chat_id_falls_back_to_untracked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    monkeypatch.setattr(
        reference,
        "infer_harness_from_untracked_session_ref",
        lambda *_args, **_kwargs: "opencode",
    )

    resolved = resolve_session_reference(repo_root, "c999")

    assert resolved.harness_session_id == "c999"
    assert resolved.harness == "opencode"
    assert resolved.tracked is False
