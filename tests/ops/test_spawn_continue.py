from pathlib import Path

import meridian.lib.ops.spawn.api as spawn_api
from meridian.lib.ops.spawn.models import SpawnActionOutput, SpawnContinueInput, SpawnCreateInput
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_state_paths


def _state_root(repo_root: Path) -> Path:
    state_root = resolve_state_paths(repo_root).root_dir
    state_root.mkdir(parents=True, exist_ok=True)
    return state_root


def _seed_spawn(
    state_root: Path,
    *,
    spawn_id: str,
    harness_session_id: str | None,
    prompt: str = "seed prompt",
    execution_cwd: str | None = None,
) -> None:
    spawn_store.start_spawn(
        state_root,
        spawn_id=spawn_id,
        chat_id="c-seed",
        model="gpt-5.3-codex",
        agent="coder",
        skills=("skill-c",),
        harness="codex",
        prompt=prompt,
        work_id="w-spawn",
        harness_session_id=harness_session_id,
        execution_cwd=execution_cwd,
    )


def test_spawn_continue_errors_when_source_spawn_lacks_harness_session_id(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_root = _state_root(repo_root)
    _seed_spawn(state_root, spawn_id="p11", harness_session_id=None)

    try:
        spawn_api.spawn_continue_sync(
            SpawnContinueInput(
                spawn_id="p11",
                prompt="follow-up prompt",
                repo_root=repo_root.as_posix(),
            )
        )
    except ValueError as exc:
        assert str(exc) == "Spawn 'p11' has no recorded session — cannot continue/fork."
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected continue from missing harness session to fail.")


def test_spawn_continue_passes_resume_details_in_legacy_and_session_dto_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_root = _state_root(repo_root)
    _seed_spawn(
        state_root,
        spawn_id="p21",
        harness_session_id="session-21",
        execution_cwd="/tmp/source-cwd",
    )

    captured_input: SpawnCreateInput | None = None

    def _fake_spawn_create_sync(
        payload: SpawnCreateInput,
        ctx=None,
        *,
        sink=None,
    ) -> SpawnActionOutput:
        _ = (ctx, sink)
        nonlocal captured_input
        captured_input = payload
        return SpawnActionOutput(command="spawn.create", status="dry-run")

    monkeypatch.setattr(spawn_api, "spawn_create_sync", _fake_spawn_create_sync)

    result = spawn_api.spawn_continue_sync(
        SpawnContinueInput(
            spawn_id="p21",
            prompt="follow-up prompt",
            fork=True,
            repo_root=repo_root.as_posix(),
        )
    )

    assert result.status == "dry-run"
    assert result.command == "spawn.continue"
    assert captured_input is not None

    # Legacy continuation fields remain populated for compatibility.
    assert captured_input.continue_harness_session_id == "session-21"
    assert captured_input.continue_harness == "codex"
    assert captured_input.continue_source_tracked is True
    assert captured_input.continue_source_ref == "p21"
    assert captured_input.continue_fork is True

    # Session DTO carries the canonical continuation payload.
    assert captured_input.session.harness_session_id == "session-21"
    assert captured_input.session.continue_fork is True
    assert captured_input.session.forked_from_chat_id == "c-seed"
    assert captured_input.session.source_execution_cwd == "/tmp/source-cwd"
