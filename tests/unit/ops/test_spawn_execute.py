from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType

import meridian.lib.ops.spawn.execute as spawn_execute
from meridian.lib.core.types import ModelId
from meridian.lib.harness.launch_spec import OpenCodeLaunchSpec
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.launch.context import LaunchContext
from meridian.lib.launch.reference import ReferenceItem
from meridian.lib.launch.request import LaunchRuntime, SpawnRequest
from meridian.lib.launch.run_inputs import ResolvedRunInputs
from meridian.lib.safety.permissions import PermissionConfig, TieredPermissionResolver


def _resolver() -> TieredPermissionResolver:
    return TieredPermissionResolver(config=PermissionConfig())


def _make_launch_context(
    *,
    tmp_path: Path,
    spec: OpenCodeLaunchSpec,
    run_inputs: ResolvedRunInputs,
) -> LaunchContext:
    request = SpawnRequest(prompt="do thing", model="gpt-5.4", harness="opencode")
    runtime = LaunchRuntime(
        state_root=(tmp_path / ".meridian").as_posix(),
        project_paths_repo_root=tmp_path.as_posix(),
        project_paths_execution_cwd=tmp_path.as_posix(),
    )
    return LaunchContext(
        request=request,
        runtime=runtime,
        repo_root=tmp_path,
        execution_cwd=tmp_path,
        state_root=tmp_path / ".meridian",
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
    )


def test_build_delivery_manifest_payload_reports_native_and_inlined_paths(tmp_path: Path) -> None:
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
        repo_root=tmp_path.as_posix(),
        reference_items=reference_items,
    )
    spec = OpenCodeLaunchSpec(
        prompt="do thing",
        permission_resolver=_resolver(),
        reference_items=reference_items,
    )
    launch_context = _make_launch_context(tmp_path=tmp_path, spec=spec, run_inputs=run_inputs)

    payload = spawn_execute._build_delivery_manifest_payload(launch_context)

    assert payload is not None
    assert payload["prompt_file"] == "prompt.md"
    assert payload["prompt_delivery_method"] == "stdin"
    assert payload["files_delivered_natively"] == [file_ref.path.as_posix()]
    assert payload["files_inlined_in_prompt"] == [
        f"{directory_ref.path.as_posix()}/",
        warning_file_ref.path.as_posix(),
    ]


def test_write_delivery_manifest_if_needed_persists_json(tmp_path: Path) -> None:
    file_ref = ReferenceItem(
        kind="file",
        path=tmp_path / "src" / "cache.py",
        body="print('cache')",
    )
    reference_items = (file_ref,)
    run_inputs = ResolvedRunInputs(
        prompt="do thing",
        model=ModelId("opencode-gpt-5.4"),
        repo_root=tmp_path.as_posix(),
        reference_items=reference_items,
    )
    spec = OpenCodeLaunchSpec(
        prompt="do thing",
        permission_resolver=_resolver(),
        reference_items=reference_items,
    )
    launch_context = _make_launch_context(tmp_path=tmp_path, spec=spec, run_inputs=run_inputs)
    log_dir = tmp_path / "spawn"
    log_dir.mkdir(parents=True)

    spawn_execute._write_delivery_manifest_if_needed(
        log_dir=log_dir,
        launch_context=launch_context,
    )

    payload = json.loads((log_dir / "delivery-manifest.json").read_text(encoding="utf-8"))
    assert payload["files_delivered_natively"] == [file_ref.path.as_posix()]

