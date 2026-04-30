import json
from pathlib import Path

import pytest

import meridian.lib.ops.spawn.api as spawn_api
from meridian.lib.launch.constants import PRIMARY_META_FILENAME
from meridian.lib.ops.spawn.models import (
    SpawnCreateInput,
    SpawnListInput,
    SpawnShowInput,
    SpawnStatsInput,
    SpawnWaitInput,
)
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_project_runtime_root_for_write


@pytest.fixture(autouse=True)
def _isolate_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERIDIAN_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")


def _state_root(project_root: Path) -> Path:
    runtime_root = resolve_project_runtime_root_for_write(project_root)
    runtime_root.mkdir(parents=True, exist_ok=True)
    return runtime_root


def _write_primary_meta(
    runtime_root: Path,
    spawn_id: str,
    *,
    activity: str,
    backend_pid: int | None = None,
    tui_pid: int | None = None,
) -> None:
    meta_path = runtime_root / "spawns" / spawn_id / PRIMARY_META_FILENAME
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(
            {
                "managed_backend": True,
                "activity": activity,
                "backend_pid": backend_pid,
                "tui_pid": tui_pid,
            }
        )
        + "\n",
        encoding="utf-8",
    )


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
    runtime_root = _state_root(project_root)

    running_id = spawn_store.start_spawn(
        runtime_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="running",
    )
    finalizing_id = spawn_store.start_spawn(
        runtime_root,
        chat_id="c2",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="finalizing",
    )
    assert spawn_store.mark_finalizing(runtime_root, finalizing_id) is True
    succeeded_id = spawn_store.start_spawn(
        runtime_root,
        chat_id="c3",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="done",
    )
    spawn_store.finalize_spawn(
        runtime_root,
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
    runtime_root = _state_root(project_root)

    spawn_id = spawn_store.start_spawn(
        runtime_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
    )
    spawn_store.record_spawn_exited(
        runtime_root,
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


def test_spawn_list_and_show_suppress_terminal_primary_activity(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    runtime_root = _state_root(project_root)

    spawn_id = spawn_store.start_spawn(
        runtime_root,
        spawn_id="p42",
        chat_id="c42",
        model="gpt-5.4",
        agent="dev-orchestrator",
        harness="codex",
        kind="primary",
        prompt="done",
        status="succeeded",
    )
    _write_primary_meta(
        runtime_root,
        str(spawn_id),
        activity="finalizing",
        backend_pid=4242,
        tui_pid=4343,
    )

    listed = spawn_api.spawn_list_sync(
        SpawnListInput(project_root=project_root.as_posix(), statuses=("succeeded",))
    )
    assert len(listed.spawns) == 1
    entry = listed.spawns[0]
    assert entry.spawn_id == "p42"
    assert entry.status == "succeeded"
    assert entry.status_display is None
    assert entry.activity is None

    detail = spawn_api.spawn_show_sync(
        SpawnShowInput(project_root=project_root.as_posix(), spawn_id="p42")
    )
    assert detail.status == "succeeded"
    assert detail.activity is None
    assert detail.backend_pid == 4242
    assert detail.tui_pid == 4343


def test_wait_yield_default_uses_shortest_harness_interval(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    runtime_root = _state_root(project_root)
    (project_root / "meridian.toml").write_text(
        "\n".join(
            [
                "[spawn]",
                "default_wait_yield_seconds = 240",
                "min_wait_yield_seconds = 30",
                "",
                "[harness.claude]",
                "wait_yield_seconds = 270",
                "",
                "[harness.codex]",
                "wait_yield_seconds = 900",
            ]
        ),
        encoding="utf-8",
    )
    claude_id = spawn_store.start_spawn(
        runtime_root,
        chat_id="c1",
        model="claude-opus-4-6",
        agent="coder",
        harness="claude",
        prompt="claude",
    )
    codex_id = spawn_store.start_spawn(
        runtime_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="codex",
    )
    unknown_id = spawn_store.start_spawn(
        runtime_root,
        chat_id="c1",
        model="other",
        agent="coder",
        harness="",
        prompt="unknown",
    )
    config = spawn_api.load_config(project_root)

    assert (
        spawn_api._resolve_wait_yield_after_seconds(
            payload=SpawnWaitInput(),
            spawn_ids=(str(claude_id), str(codex_id)),
            project_root=project_root,
            config=config,
        )
        == 270.0
    )
    assert (
        spawn_api._resolve_wait_yield_after_seconds(
            payload=SpawnWaitInput(),
            spawn_ids=(str(codex_id), str(unknown_id)),
            project_root=project_root,
            config=config,
        )
        == 240.0
    )


def test_wait_yield_override_wins_over_harness_defaults(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    runtime_root = _state_root(project_root)
    spawn_id = spawn_store.start_spawn(
        runtime_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="codex",
    )
    config = spawn_api.load_config(project_root)

    assert (
        spawn_api._resolve_wait_yield_after_seconds(
            payload=SpawnWaitInput(yield_after_secs=12),
            spawn_ids=(str(spawn_id),),
            project_root=project_root,
            config=config,
        )
        == 12
    )
