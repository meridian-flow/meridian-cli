from __future__ import annotations

import json

# pyright: reportPrivateUsage=false
import re
import signal
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest

from meridian.lib.config.settings import load_config
from meridian.lib.core.types import HarnessId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.launch import process
from meridian.lib.launch.constants import DEFAULT_INFRA_EXIT_CODE
from meridian.lib.launch.context import build_launch_context
from meridian.lib.launch.request import (
    LaunchArgvIntent,
    LaunchCompositionSurface,
    LaunchRuntime,
    SessionRequest,
    SpawnRequest,
)
from meridian.lib.launch.types import SessionMode


def test_sync_pty_winsize_copies_source_size(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int, bytes]] = []
    packed = b"winsize-bytes"

    def fake_ioctl(fd: int, op: int, payload: bytes) -> bytes:
        calls.append((fd, op, payload))
        if op == process.termios.TIOCGWINSZ:
            return packed
        return b""

    monkeypatch.setattr(process.fcntl, "ioctl", fake_ioctl)

    process._sync_pty_winsize(source_fd=10, target_fd=11)

    assert calls == [
        (10, process.termios.TIOCGWINSZ, process.struct.pack("HHHH", 0, 0, 0, 0)),
        (11, process.termios.TIOCSWINSZ, packed),
    ]


def test_install_winsize_forwarding_syncs_immediately_and_restores(
    monkeypatch: pytest.MonkeyPatch,
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

    monkeypatch.setattr(
        process,
        "_sync_pty_winsize",
        fake_sync_pty_winsize,
    )
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


def test_run_harness_process_fork_uses_new_chat_and_materialized_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("MERIDIAN_CHAT_ID", raising=False)
    repo_root = tmp_path
    (repo_root / "mars.toml").write_text(
        "[settings]\n"
        'targets = [".agents"]\n',
        encoding="utf-8",
    )
    harness_registry = get_default_harness_registry()
    config = load_config(repo_root)
    codex_adapter = harness_registry.get_subprocess_harness(HarnessId.CODEX)
    launch_context = build_launch_context(
        spawn_id="dry-run-primary",
        request=SpawnRequest(
            prompt="fork prompt",
            prompt_is_composed=False,
            model="gpt-5.4",
            harness=HarnessId.CODEX.value,
            session=SessionRequest(
                requested_harness_session_id="source-session",
                continue_chat_id="c7",
                forked_from_chat_id="c7",
                continue_fork=True,
                primary_session_mode=SessionMode.FORK.value,
            ),
        ),
        runtime=LaunchRuntime(
            argv_intent=LaunchArgvIntent.REQUIRED,
            composition_surface=LaunchCompositionSurface.PRIMARY,
            config_snapshot=config.model_dump(mode="json", exclude_none=True),
            state_root=(tmp_path / ".meridian").as_posix(),
            project_paths_repo_root=repo_root.as_posix(),
            project_paths_execution_cwd=repo_root.as_posix(),
        ),
        harness_registry=harness_registry,
        dry_run=True,
    )

    captured: dict[str, str | None] = {}

    def fake_build_command(run: SpawnParams, perms: object) -> list[str]:
        _ = perms
        captured["build_continue_session"] = run.continue_harness_session_id
        return ["codex", "resume", run.continue_harness_session_id or ""]

    def fake_fork_session(source_session_id: str) -> str:
        captured["fork_source_session"] = source_session_id
        return "forked-session"

    def fake_run_primary_process_with_capture(**kwargs: object) -> tuple[int, int]:
        captured["command_session"] = tuple(kwargs["command"])[2]
        captured["env_chat_id"] = dict(kwargs["env"]).get("MERIDIAN_CHAT_ID")
        started = kwargs.get("on_child_started")
        assert callable(started)
        started(111)
        return (0, 111)

    def fake_start_session(
        state_root: Path,
        harness: str,
        harness_session_id: str | None,
        model: str,
        chat_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        _ = (state_root, harness, model)
        captured["chat_id_arg"] = chat_id
        captured["start_harness_session_id"] = harness_session_id
        captured["forked_from_chat_id"] = kwargs.get("forked_from_chat_id")
        return "c999"

    monkeypatch.setattr(codex_adapter, "build_command", fake_build_command)
    monkeypatch.setattr(codex_adapter, "fork_session", fake_fork_session)
    monkeypatch.setattr(codex_adapter, "observe_session_id", lambda **kwargs: "forked-session")
    monkeypatch.setattr(
        process,
        "_run_primary_process_with_capture",
        fake_run_primary_process_with_capture,
    )
    monkeypatch.setattr(process, "stop_session", lambda *args, **kwargs: None)
    monkeypatch.setattr(process, "update_session_harness_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(process, "start_session", fake_start_session)

    outcome = process.run_harness_process(launch_context, harness_registry)

    assert captured["fork_source_session"] == "source-session"
    assert captured["build_continue_session"] == "forked-session"
    assert captured["command_session"] == "forked-session"
    assert captured["chat_id_arg"] is None
    # I-10: session is created with the SOURCE session ID; fork happens after the row exists.
    assert captured["start_harness_session_id"] == "source-session"
    assert captured["forked_from_chat_id"] == "c7"
    assert captured["env_chat_id"] == "c999"
    assert outcome.chat_id == "c999"
    events = [
        json.loads(line)
        for line in (launch_context.state_root / "spawns.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    finalize_events = [event for event in events if event.get("event") == "finalize"]
    assert len(finalize_events) == 1
    assert finalize_events[0]["origin"] == "launcher"


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


def test_build_launch_context_dry_run_runtime_share_same_argv_for_raw_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("MERIDIAN_HARNESS_COMMAND", raising=False)
    request = _build_spawn_request()
    runtime = _build_launch_runtime(tmp_path=tmp_path)
    registry = get_default_harness_registry()

    runtime_ctx = build_launch_context(
        spawn_id="p-ctx",
        request=request,
        runtime=runtime,
        harness_registry=registry,
        dry_run=False,
    )
    dry_run_ctx = build_launch_context(
        spawn_id="p-ctx",
        request=request,
        runtime=runtime,
        harness_registry=registry,
        dry_run=True,
    )

    assert runtime_ctx.argv == dry_run_ctx.argv
    assert runtime_ctx.is_bypass is False
    assert dry_run_ctx.is_bypass is False


def test_build_launch_context_bypass_command_owned_by_factory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("MERIDIAN_HARNESS_COMMAND", raising=False)
    request = _build_spawn_request(extra_args=("--json", "--verbose"))
    runtime = _build_launch_runtime(tmp_path=tmp_path, override="codex exec")
    registry = get_default_harness_registry()

    runtime_ctx = build_launch_context(
        spawn_id="p-ctx",
        request=request,
        runtime=runtime,
        harness_registry=registry,
        dry_run=False,
    )
    dry_run_ctx = build_launch_context(
        spawn_id="p-ctx",
        request=request,
        runtime=runtime,
        harness_registry=registry,
        dry_run=True,
    )

    assert runtime_ctx.is_bypass is True
    assert dry_run_ctx.is_bypass is True
    assert runtime_ctx.argv == ("codex", "exec", "--json", "--verbose")
    assert runtime_ctx.argv == dry_run_ctx.argv


def test_build_launch_context_spec_only_tolerates_argv_build_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request = _build_spawn_request()
    runtime = _build_launch_runtime(
        tmp_path=tmp_path,
        argv_intent=LaunchArgvIntent.SPEC_ONLY,
    )
    registry = get_default_harness_registry()

    def fail_build_launch_argv(**_: object) -> tuple[str, ...]:
        raise RuntimeError("argv unavailable")

    monkeypatch.setattr("meridian.lib.launch.context.build_launch_argv", fail_build_launch_argv)

    launch_ctx = build_launch_context(
        spawn_id="p-spec-only",
        request=request,
        runtime=runtime,
        harness_registry=registry,
    )

    assert launch_ctx.argv == ()
    assert launch_ctx.spec is not None


def test_shared_runner_constants_defined_once() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source_root = repo_root / "src"
    constants_path = source_root / "meridian/lib/launch/constants.py"

    patterns = {
        "DEFAULT_INFRA_EXIT_CODE": r"^DEFAULT_INFRA_EXIT_CODE\b.*=",
        "OUTPUT_FILENAME": r"^OUTPUT_FILENAME\b.*=",
        "STDERR_FILENAME": r"^STDERR_FILENAME\b.*=",
        "TOKENS_FILENAME": r"^TOKENS_FILENAME\b.*=",
        "REPORT_FILENAME": r"^REPORT_FILENAME\b.*=",
    }

    for name, pattern in patterns.items():
        matches: list[Path] = []
        for path in source_root.rglob("*.py"):
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if re.search(pattern, line):
                    matches.append(path)
                    break
        assert matches == [constants_path], f"{name} defined outside constants.py: {matches}"

    streaming_source = (
        source_root / "meridian/lib/launch/streaming_runner.py"
    ).read_text(encoding="utf-8")
    assert "DEFAULT_INFRA_EXIT_CODE =" not in streaming_source
    assert DEFAULT_INFRA_EXIT_CODE == 2
