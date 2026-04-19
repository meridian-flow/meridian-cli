from __future__ import annotations

import signal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from meridian.lib.core.types import HarnessId
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.launch import process
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
        state_root=(tmp_path / ".meridian").as_posix(),
        project_paths_repo_root=tmp_path.as_posix(),
        project_paths_execution_cwd=tmp_path.as_posix(),
    )


def test_install_winsize_forwarding_syncs_immediately_and_restores(
    monkeypatch: MonkeyPatch,
) -> None:
    sync_calls: list[tuple[int, int]] = []
    installed_handlers: list[tuple[int, object]] = []
    previous_handler = signal.SIG_IGN

    def fake_sync_pty_winsize(*, source_fd: int, target_fd: int) -> None:
        sync_calls.append((source_fd, target_fd))

    def fake_getsignal(signum: int) -> object:
        _ = signum
        return previous_handler

    def fake_signal(signum: int, handler: object) -> None:
        installed_handlers.append((signum, handler))

    monkeypatch.setattr(process, "_sync_pty_winsize", fake_sync_pty_winsize)
    monkeypatch.setattr(process.signal, "getsignal", fake_getsignal)
    monkeypatch.setattr(process.signal, "signal", fake_signal)

    restore = process._install_winsize_forwarding(source_fd=20, target_fd=21)

    assert sync_calls == [(20, 21)]
    assert installed_handlers[0][0] == signal.SIGWINCH

    handler = installed_handlers[0][1]
    assert callable(handler)
    handler(signal.SIGWINCH, None)

    assert sync_calls == [(20, 21), (20, 21)]

    restore()

    assert installed_handlers[-1] == (signal.SIGWINCH, previous_handler)


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
