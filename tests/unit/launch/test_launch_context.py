from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from meridian.lib.core.child_env import ALLOWED_CHILD_ENV_KEYS
from meridian.lib.core.types import HarnessId
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.launch.context import build_launch_context
from meridian.lib.launch.request import (
    LaunchArgvIntent,
    LaunchCompositionSurface,
    LaunchRuntime,
    SpawnRequest,
)

if TYPE_CHECKING:
    from pytest import MonkeyPatch


def _build_spawn_request(
    prompt: str = "hello",
    extra_args: tuple[str, ...] = (),
) -> SpawnRequest:
    return SpawnRequest(
        model="gpt-5.4",
        harness=HarnessId.CODEX.value,
        prompt=prompt,
        extra_args=extra_args,
    )


def _build_launch_runtime(
    *,
    tmp_path: Path,
    override: str | None = None,
    argv_intent: LaunchArgvIntent = LaunchArgvIntent.REQUIRED,
    composition_surface: LaunchCompositionSurface = LaunchCompositionSurface.DIRECT,
    execution_cwd: Path | None = None,
) -> LaunchRuntime:
    resolved_execution_cwd = execution_cwd or tmp_path
    return LaunchRuntime(
        argv_intent=argv_intent,
        composition_surface=composition_surface,
        harness_command_override=override,
        report_output_path=(tmp_path / "report.md").as_posix(),
        runtime_root=(tmp_path / ".meridian").as_posix(),
        project_paths_project_root=tmp_path.as_posix(),
        project_paths_execution_cwd=resolved_execution_cwd.as_posix(),
    )


def _write_minimal_mars_config(project_root: Path) -> None:
    (project_root / "mars.toml").write_text(
        "[settings]\n"
        'targets = [".agents"]\n',
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    (
        "extra_args",
        "override",
        "argv_intent",
        "patch_argv_failure",
        "expected_argv",
        "expected_bypass",
        "compare_dry_run",
    ),
    [
        pytest.param(
            (),
            None,
            LaunchArgvIntent.REQUIRED,
            False,
            None,
            False,
            True,
            id="raw-request-runtime-dry-run-share-argv",
        ),
        pytest.param(
            ("--json", "--verbose"),
            "codex exec",
            LaunchArgvIntent.REQUIRED,
            False,
            ("codex", "exec", "--json", "--verbose"),
            True,
            True,
            id="bypass-command-owned-by-factory",
        ),
        pytest.param(
            (),
            None,
            LaunchArgvIntent.SPEC_ONLY,
            True,
            (),
            False,
            False,
            id="spec-only-tolerates-argv-build-failure",
        ),
    ],
)
def test_build_launch_context_behaviors(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    extra_args: tuple[str, ...],
    override: str | None,
    argv_intent: LaunchArgvIntent,
    patch_argv_failure: bool,
    expected_argv: tuple[str, ...] | None,
    expected_bypass: bool,
    compare_dry_run: bool,
) -> None:
    monkeypatch.delenv("MERIDIAN_HARNESS_COMMAND", raising=False)
    request = _build_spawn_request(extra_args=extra_args)
    runtime = _build_launch_runtime(
        tmp_path=tmp_path,
        override=override,
        argv_intent=argv_intent,
    )
    registry = get_default_harness_registry()

    if patch_argv_failure:
        def fail_build_launch_argv(**_: object) -> tuple[str, ...]:
            raise RuntimeError("argv unavailable")

        monkeypatch.setattr(
            "meridian.lib.launch.context.build_launch_argv",
            fail_build_launch_argv,
        )

    runtime_ctx = build_launch_context(
        spawn_id="p-ctx",
        request=request,
        runtime=runtime,
        harness_registry=registry,
        dry_run=False,
    )
    assert runtime_ctx.is_bypass is expected_bypass

    if compare_dry_run:
        dry_run_ctx = build_launch_context(
            spawn_id="p-ctx",
            request=request,
            runtime=runtime,
            harness_registry=registry,
            dry_run=True,
        )
        assert runtime_ctx.argv == dry_run_ctx.argv
        assert dry_run_ctx.is_bypass is expected_bypass

    if expected_argv is not None:
        assert runtime_ctx.argv == expected_argv

    if patch_argv_failure:
        assert runtime_ctx.spec is not None


def test_build_launch_context_projects_runtime_child_env_paths(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("MERIDIAN_HARNESS_COMMAND", raising=False)
    monkeypatch.setenv("MERIDIAN_CHAT_ID", "c-parent")
    monkeypatch.setenv("MERIDIAN_DEPTH", "2")
    monkeypatch.setenv("MERIDIAN_WORK_ID", "work-alpha")
    request = _build_spawn_request()
    runtime = _build_launch_runtime(tmp_path=tmp_path)

    runtime_ctx = build_launch_context(
        spawn_id="p-child-env",
        request=request,
        runtime=runtime,
        harness_registry=get_default_harness_registry(),
        dry_run=True,
    )

    assert runtime_ctx.env_overrides["MERIDIAN_DEPTH"] == "3"
    assert runtime_ctx.env_overrides["MERIDIAN_SPAWN_ID"] == "p-child-env"
    assert runtime_ctx.env_overrides["MERIDIAN_CHAT_ID"] == "c-parent"
    assert runtime_ctx.env_overrides["MERIDIAN_PROJECT_DIR"] == tmp_path.as_posix()
    assert runtime_ctx.env_overrides["MERIDIAN_RUNTIME_DIR"] == (
        tmp_path / ".meridian"
    ).as_posix()
    assert runtime_ctx.env_overrides["MERIDIAN_WORK_ID"] == "work-alpha"
    assert runtime_ctx.env_overrides["MERIDIAN_WORK_DIR"] == (
        tmp_path / ".meridian" / "work" / "work-alpha"
    ).as_posix()
    assert runtime_ctx.env_overrides["MERIDIAN_KB_DIR"] == (
        tmp_path / ".meridian" / "kb"
    ).as_posix()
    assert runtime_ctx.env_overrides["MERIDIAN_FS_DIR"] == (
        tmp_path / ".meridian" / "kb"
    ).as_posix()
    assert set(runtime_ctx.env_overrides) <= ALLOWED_CHILD_ENV_KEYS


@pytest.mark.parametrize(
    ("parent_depth", "expected_depth"),
    [
        pytest.param(None, "0", id="clean-shell-primary-root"),
        pytest.param("2", "2", id="primary-launched-from-existing-depth"),
    ],
)
def test_build_launch_context_primary_preserves_runtime_depth(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    parent_depth: str | None,
    expected_depth: str,
) -> None:
    _write_minimal_mars_config(tmp_path)
    monkeypatch.delenv("MERIDIAN_HARNESS_COMMAND", raising=False)
    monkeypatch.delenv("MERIDIAN_DEPTH", raising=False)
    monkeypatch.delenv("MERIDIAN_SPAWN_ID", raising=False)
    if parent_depth is not None:
        monkeypatch.setenv("MERIDIAN_DEPTH", parent_depth)
    request = _build_spawn_request()
    runtime = _build_launch_runtime(
        tmp_path=tmp_path,
        composition_surface=LaunchCompositionSurface.PRIMARY,
    )

    runtime_ctx = build_launch_context(
        spawn_id="p-primary",
        request=request,
        runtime=runtime,
        harness_registry=get_default_harness_registry(),
        dry_run=True,
    )

    assert runtime_ctx.env_overrides["MERIDIAN_DEPTH"] == expected_depth
    assert runtime_ctx.env_overrides["MERIDIAN_SPAWN_ID"] == "p-primary"
    assert "MERIDIAN_PARENT_SPAWN_ID" not in runtime_ctx.env_overrides


def test_build_launch_context_env_keeps_project_root_when_execution_cwd_differs(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("MERIDIAN_HARNESS_COMMAND", raising=False)
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    execution_cwd = tmp_path / ".meridian" / "spawns" / "p-parent"
    execution_cwd.mkdir(parents=True)
    request = _build_spawn_request()
    runtime = _build_launch_runtime(tmp_path=tmp_path, execution_cwd=execution_cwd)

    runtime_ctx = build_launch_context(
        spawn_id="p-child-env",
        request=request,
        runtime=runtime,
        harness_registry=get_default_harness_registry(),
        dry_run=True,
    )

    assert runtime_ctx.execution_cwd == execution_cwd
    assert runtime_ctx.env_overrides["MERIDIAN_PROJECT_DIR"] == tmp_path.as_posix()
    assert runtime_ctx.env_overrides["MERIDIAN_KB_DIR"] == (
        tmp_path / ".meridian" / "kb"
    ).as_posix()


def test_build_launch_context_emits_child_spawn_id(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("MERIDIAN_HARNESS_COMMAND", raising=False)
    monkeypatch.setenv("MERIDIAN_SPAWN_ID", "p-parent")
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    request = _build_spawn_request()
    runtime = _build_launch_runtime(tmp_path=tmp_path)

    runtime_ctx = build_launch_context(
        spawn_id="p-child",
        request=request,
        runtime=runtime,
        harness_registry=get_default_harness_registry(),
        dry_run=True,
    )

    assert runtime_ctx.env_overrides["MERIDIAN_SPAWN_ID"] == "p-child"
    assert runtime_ctx.env_overrides["MERIDIAN_PARENT_SPAWN_ID"] == "p-parent"
