from pathlib import Path

import pytest

import meridian.lib.ops.spawn.api as spawn_api
from meridian.lib.ops.spawn.models import SpawnCreateInput, SpawnListInput, SpawnStatsInput
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_project_runtime_root_for_write


@pytest.fixture(autouse=True)
def _isolate_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERIDIAN_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")


def _state_root(project_root: Path) -> Path:
    state_root = resolve_project_runtime_root_for_write(project_root)
    state_root.mkdir(parents=True, exist_ok=True)
    return state_root


def test_spawn_create_dry_run_resolves_project_root_from_nested_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "repo"
    nested = project_root / "src" / "feature"
    (project_root / ".agents" / "skills").mkdir(parents=True)
    nested.mkdir(parents=True)
    reference_file = project_root / "guide.md"
    reference_file.write_text("# Guide\n", encoding="utf-8")
    monkeypatch.chdir(nested)

    result = spawn_api.spawn_create_sync(
        SpawnCreateInput(
            prompt="run",
            model="",
            files=("guide.md",),
            dry_run=True,
        )
    )

    assert result.status == "dry-run"
    resolved_reference = reference_file.resolve()
    assert len(result.reference_files) == 1
    assert Path(result.reference_files[0]).resolve() == resolved_reference
    composed_prompt = result.composed_prompt or ""
    assert (
        str(resolved_reference) in composed_prompt
        or resolved_reference.as_posix() in composed_prompt
    )


def test_spawn_stats_includes_finalizing_bucket(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    state_root = _state_root(project_root)

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
        SpawnStatsInput(project_root=project_root.as_posix())
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
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    state_root = _state_root(project_root)

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
        SpawnListInput(project_root=project_root.as_posix(), statuses=("running",))
    )

    assert len(output.spawns) == 1
    assert output.spawns[0].status == "running"
    assert output.spawns[0].status_display is None
