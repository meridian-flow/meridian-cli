from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from meridian.lib.core.child_env import ALLOWED_CHILD_ENV_KEYS
from meridian.lib.core.types import HarnessId
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.launch.context import build_launch_context
from meridian.lib.launch.request import LaunchArgvIntent, LaunchRuntime, SpawnRequest

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
) -> LaunchRuntime:
    return LaunchRuntime(
        argv_intent=argv_intent,
        harness_command_override=override,
        report_output_path=(tmp_path / "report.md").as_posix(),
        runtime_root=(tmp_path / ".meridian").as_posix(),
        project_paths_project_root=tmp_path.as_posix(),
        project_paths_execution_cwd=tmp_path.as_posix(),
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
