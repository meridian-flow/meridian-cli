from pathlib import Path
from types import SimpleNamespace

import meridian.lib.ops.spawn.api as spawn_api
from meridian.lib.ops.spawn.models import SpawnCreateInput, SpawnListInput, SpawnStatsInput
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_runtime_state_root


def test_spawn_create_validates_model_against_resolved_runtime_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    raw_root = tmp_path / "nested" / "cwd"
    resolved_root = tmp_path / "repo-root"
    call_order: list[str] = []
    seen_validation_root: str | None = None

    def _fake_resolve_repo_root_input(repo_root: str | None):
        nonlocal call_order
        _ = repo_root
        call_order.append("resolve")
        return resolved_root

    def _fake_validate_create_input(payload: SpawnCreateInput):
        nonlocal call_order, seen_validation_root
        call_order.append("validate")
        seen_validation_root = payload.repo_root
        return payload, "preflight warning"

    def _fake_build_create_payload(
        payload: SpawnCreateInput,
        *,
        runtime=None,
        preflight_warning: str | None = None,
        ctx=None,
    ):
        _ = (payload, runtime, ctx)
        return SimpleNamespace(
            model="gpt-5.3-codex",
            harness="codex",
            agent=None,
            warning=preflight_warning,
            agent_metadata={},
            skills=(),
            skill_paths=(),
            reference_files=(),
            template_vars={},
            context_from=None,
            prompt="prompt",
            cli_command=(),
        )

    monkeypatch.setattr(spawn_api, "_resolve_repo_root_input", _fake_resolve_repo_root_input)
    monkeypatch.setattr(spawn_api, "validate_create_input", _fake_validate_create_input)
    monkeypatch.setattr(spawn_api, "build_create_payload", _fake_build_create_payload)
    monkeypatch.setattr(spawn_api, "load_config", lambda _: object())

    result = spawn_api.spawn_create_sync(
        SpawnCreateInput(
            prompt="run",
            model="gpt-5.3-codex",
            repo_root=raw_root.as_posix(),
            dry_run=True,
        )
    )

    assert result.status == "dry-run"
    assert result.warning == "preflight warning"
    assert call_order == ["resolve", "validate"]
    assert seen_validation_root == resolved_root.as_posix()


def test_spawn_stats_includes_finalizing_bucket(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_root = resolve_runtime_state_root(repo_root)

    running_id = spawn_store.start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="running",
    )
    finalizing_id = spawn_store.start_spawn(
        state_root,
        chat_id="c2",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="finalizing",
    )
    assert spawn_store.mark_finalizing(state_root, finalizing_id) is True
    succeeded_id = spawn_store.start_spawn(
        state_root,
        chat_id="c3",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="done",
    )
    spawn_store.finalize_spawn(
        state_root,
        succeeded_id,
        status="succeeded",
        exit_code=0,
        origin="runner",
    )

    output = spawn_api.spawn_stats_sync(
        SpawnStatsInput(repo_root=repo_root.as_posix())
    )

    assert output.total_runs == 3
    assert output.running == 1
    assert output.finalizing == 1
    assert output.succeeded == 1
    model_stats = output.models["gpt-5.4"]
    assert model_stats.running == 1
    assert model_stats.finalizing == 1
    assert running_id != finalizing_id


def test_spawn_list_does_not_infer_running_star_from_exited_at(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_root = resolve_runtime_state_root(repo_root)

    spawn_id = spawn_store.start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
    )
    spawn_store.record_spawn_exited(
        state_root,
        spawn_id,
        exit_code=143,
        exited_at="2026-04-13T10:00:00Z",
    )

    output = spawn_api.spawn_list_sync(
        SpawnListInput(repo_root=repo_root.as_posix(), statuses=("running",))
    )

    assert len(output.spawns) == 1
    assert output.spawns[0].status == "running"
    assert output.spawns[0].status_display is None
