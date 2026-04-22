from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from meridian.lib.config.project_paths import ProjectConfigPaths
from meridian.lib.core.types import ModelId, SpawnId
from meridian.lib.harness.launch_spec import OpenCodeLaunchSpec
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.launch.artifact_io import write_projection_artifacts
from meridian.lib.launch.composition import (
    ProjectedContent,
    ProjectionChannels,
    ReferenceRouting,
)
from meridian.lib.launch.context import LaunchContext
from meridian.lib.launch.reference import ReferenceItem
from meridian.lib.launch.request import LaunchRuntime, SpawnRequest
from meridian.lib.launch.run_inputs import ResolvedRunInputs
from meridian.lib.ops.spawn import execute as spawn_execute
from meridian.lib.ops.spawn.execute import _write_params_json
from meridian.lib.safety.permissions import PermissionConfig, TieredPermissionResolver


def _resolver() -> TieredPermissionResolver:
    return TieredPermissionResolver(config=PermissionConfig())


def _make_launch_context(
    *,
    tmp_path: Path,
    spec: OpenCodeLaunchSpec,
    run_inputs: ResolvedRunInputs,
    projected: ProjectedContent | None = None,
) -> LaunchContext:
    request = SpawnRequest(prompt=run_inputs.prompt, model="gpt-5.4", harness="opencode")
    runtime = LaunchRuntime(
        runtime_root=(tmp_path / ".meridian").as_posix(),
        project_paths_project_root=tmp_path.as_posix(),
        project_paths_execution_cwd=tmp_path.as_posix(),
    )
    return LaunchContext(
        request=request,
        runtime=runtime,
        project_root=tmp_path,
        execution_cwd=tmp_path,
        runtime_root=tmp_path / ".meridian",
        work_id=None,
        argv=("opencode", "run", "-"),
        run_params=run_inputs,
        perms=_resolver(),
        spec=spec,
        child_cwd=tmp_path,
        env=MappingProxyType({}),
        env_overrides=MappingProxyType({}),
        report_output_path=tmp_path / "report.md",
        harness=OpenCodeAdapter(),
        resolved_request=request,
        projected_content=projected,
    )


def test_write_projection_artifacts_uses_projected_content_for_spawn(tmp_path: Path) -> None:
    file_ref = ReferenceItem(
        kind="file",
        path=tmp_path / "src" / "auth.py",
        body="print('ok')",
    )
    directory_ref = ReferenceItem(
        kind="directory",
        path=tmp_path / "src",
        body="tree",
    )
    warning_file_ref = ReferenceItem(
        kind="file",
        path=tmp_path / "src" / "binary.dat",
        body="",
        warning="Binary file: 10KB",
    )
    reference_items = (file_ref, directory_ref, warning_file_ref)
    run_inputs = ResolvedRunInputs(
        prompt="do thing",
        model=ModelId("opencode-gpt-5.4"),
        project_root=tmp_path.as_posix(),
        reference_items=reference_items,
    )
    spec = OpenCodeLaunchSpec(
        prompt="do thing",
        permission_resolver=_resolver(),
    )
    projected = ProjectedContent(
        system_prompt="",
        user_turn_content="projected spawn",
        reference_routing=(
            ReferenceRouting(
                path=file_ref.path.as_posix(),
                type="file",
                routing="native-injection",
                native_flag=f"--file {file_ref.path.as_posix()}",
            ),
        ),
        channels=ProjectionChannels(
            system_instruction="inline",
            user_task_prompt="inline",
            task_context="native-injection",
        ),
    )
    launch_context = _make_launch_context(
        tmp_path=tmp_path,
        spec=spec,
        run_inputs=run_inputs,
        projected=projected,
    )
    log_dir = tmp_path / "spawn"
    log_dir.mkdir(parents=True)

    write_projection_artifacts(log_dir=log_dir, launch_context=launch_context, surface="spawn")

    assert not (log_dir / "prompt.md").exists()
    references_payload = json.loads((log_dir / "references.json").read_text(encoding="utf-8"))
    assert references_payload == [
        {
            "path": file_ref.path.as_posix(),
            "type": "file",
            "routing": "native-injection",
            "native_flag": f"--file {file_ref.path.as_posix()}",
        },
    ]
    assert json.loads((log_dir / "projection-manifest.json").read_text(encoding="utf-8")) == {
        "harness": "opencode",
        "surface": "spawn",
        "channels": {
            "system_instruction": "inline",
            "user_task_prompt": "inline",
            "task_context": "native-injection",
        },
    }


def test_write_projection_artifacts_uses_projected_content_for_primary(tmp_path: Path) -> None:
    run_inputs = ResolvedRunInputs(
        prompt="fallback prompt",
        model=ModelId("gpt-5.4"),
        appended_system_prompt="fallback system",
        user_turn_content="fallback user",
    )
    spec = OpenCodeLaunchSpec(prompt="fallback prompt", permission_resolver=_resolver())
    projected = ProjectedContent(
        system_prompt="projected system",
        user_turn_content="projected user",
        reference_routing=(),
        channels=ProjectionChannels(
            system_instruction="none",
            user_task_prompt="inline",
            task_context="inline",
        ),
    )
    launch_context = _make_launch_context(
        tmp_path=tmp_path,
        spec=spec,
        run_inputs=run_inputs,
        projected=projected,
    )
    log_dir = tmp_path / "primary"
    log_dir.mkdir(parents=True)

    write_projection_artifacts(log_dir=log_dir, launch_context=launch_context, surface="primary")

    assert (log_dir / "system-prompt.md").read_text(encoding="utf-8") == "projected system"
    assert (log_dir / "starting-prompt.md").read_text(encoding="utf-8") == "projected user"
    assert json.loads((log_dir / "projection-manifest.json").read_text(encoding="utf-8")) == {
        "harness": "opencode",
        "surface": "primary",
        "channels": {
            "system_instruction": "none",
            "user_task_prompt": "inline",
            "task_context": "inline",
        },
    }


def test_write_params_json_does_not_write_legacy_prompt_md(tmp_path: Path) -> None:
    project_paths = ProjectConfigPaths(project_root=tmp_path, execution_cwd=tmp_path)
    spawn_id = SpawnId("p123")
    request = SpawnRequest(prompt="prompt", model="gpt-5.4", harness="codex")

    _write_params_json(project_paths, spawn_id, request)

    log_dir = tmp_path / ".meridian" / "spawns" / str(spawn_id)
    assert (log_dir / "params.json").exists()
    assert not (log_dir / "prompt.md").exists()


def test_background_worker_main_uses_project_root_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = (tmp_path / "project").resolve()
    project_root.mkdir()
    observed_project_root: dict[str, Path] = {}
    finalized: dict[str, object] = {}

    def fake_resolve_project_config_paths(*, project_root: Path) -> ProjectConfigPaths:
        observed_project_root["value"] = project_root
        return ProjectConfigPaths(project_root=project_root, execution_cwd=project_root)

    class _FakeLifecycleService:
        def finalize(self, spawn_id: str, **kwargs: object) -> None:
            finalized["spawn_id"] = spawn_id
            finalized["status"] = kwargs.get("status")

    def fake_load_bg_worker_request(_log_dir: Path) -> spawn_execute.BackgroundWorkerLaunchRequest:
        raise RuntimeError("missing launch payload")

    monkeypatch.setattr(
        spawn_execute,
        "resolve_project_config_paths",
        fake_resolve_project_config_paths,
    )
    monkeypatch.setattr(
        spawn_execute,
        "resolve_runtime_root",
        lambda _project_root: tmp_path / ".meridian",
    )
    monkeypatch.setattr(
        spawn_execute,
        "resolve_spawn_log_dir",
        lambda _project_root, _spawn_id: tmp_path / "logs",
    )
    monkeypatch.setattr(
        spawn_execute,
        "create_lifecycle_service",
        lambda _project_root, _runtime_root: _FakeLifecycleService(),
    )
    monkeypatch.setattr(
        spawn_execute,
        "_load_bg_worker_request",
        fake_load_bg_worker_request,
    )

    exit_code = spawn_execute._background_worker_main(
        ["--spawn-id", "p123", "--project-root", project_root.as_posix()]
    )

    assert exit_code == 1
    assert observed_project_root["value"] == project_root
    assert finalized["spawn_id"] == "p123"
    assert finalized["status"] == "failed"
