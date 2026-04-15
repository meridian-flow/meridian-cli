from __future__ import annotations

import json

# pyright: reportPrivateUsage=false
import re
import signal
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from meridian.lib.config.settings import load_config
from meridian.lib.core.domain import Spawn
from meridian.lib.core.types import HarnessId, ModelId, SpawnId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.launch import process
from meridian.lib.launch.constants import DEFAULT_INFRA_EXIT_CODE
from meridian.lib.launch.context import (
    LaunchContext,
    prepare_launch_context,
)
from meridian.lib.launch.plan import ResolvedPrimaryLaunchPlan
from meridian.lib.launch.types import LaunchRequest, PrimarySessionMetadata, SessionMode
from meridian.lib.ops.spawn.plan import ExecutionPolicy, PreparedSpawnPlan, SessionContinuation
from meridian.lib.safety.permissions import PermissionConfig, TieredPermissionResolver


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
    repo_root = tmp_path
    harness_registry = get_default_harness_registry()
    config = load_config(repo_root)
    codex_adapter = harness_registry.get_subprocess_harness(HarnessId.CODEX)
    request = LaunchRequest(
        model="gpt-5.4",
        harness="codex",
        session_mode=SessionMode.FORK,
        session=SessionContinuation(
            harness_session_id="source-session",
            continue_chat_id="c7",
            forked_from_chat_id="c7",
            continue_fork=True,
        ),
    )
    plan = ResolvedPrimaryLaunchPlan(
        repo_root=repo_root,
        state_root=tmp_path / ".meridian",
        prompt="fork prompt",
        request=request,
        config=config,
        adapter=codex_adapter,
        session_metadata=PrimarySessionMetadata(
            harness="codex",
            model="gpt-5.4",
            agent="",
            agent_path="",
            skills=(),
            skill_paths=(),
        ),
        run_params=SpawnParams(
            prompt="fork prompt",
            model=ModelId("gpt-5.4"),
            interactive=True,
            continue_harness_session_id="source-session",
            continue_fork=True,
        ),
        permission_config=PermissionConfig(),
        permission_resolver=TieredPermissionResolver(config=PermissionConfig()),
        command=("codex", "resume", "source-session"),
        seed_harness_session_id="source-session",
        command_request=request,
    )

    captured: dict[str, str | None] = {}

    def fake_build_command(run: SpawnParams, perms: object) -> list[str]:
        _ = perms
        captured["build_continue_session"] = run.continue_harness_session_id
        return ["codex", "resume", run.continue_harness_session_id or ""]

    def fake_fork_session(source_session_id: str) -> str:
        captured["fork_source_session"] = source_session_id
        return "forked-session"

    def fake_build_launch_env(*args: object, **kwargs: object) -> dict[str, str]:
        _ = args, kwargs
        return {}

    def fake_run_primary_process_with_capture(**kwargs: object) -> tuple[int, int]:
        captured["command_session"] = tuple(kwargs["command"])[2]
        started = kwargs.get("on_child_started")
        assert callable(started)
        started(111)
        return (0, 111)

    def fake_extract_latest_session_id(**kwargs: object) -> str:
        _ = kwargs
        return "forked-session"

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
    monkeypatch.setattr(process, "build_launch_env", fake_build_launch_env)
    monkeypatch.setattr(
        process,
        "_run_primary_process_with_capture",
        fake_run_primary_process_with_capture,
    )
    monkeypatch.setattr(process, "extract_latest_session_id", fake_extract_latest_session_id)
    monkeypatch.setattr(process, "stop_session", lambda *args, **kwargs: None)
    monkeypatch.setattr(process, "update_session_harness_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(process, "start_session", fake_start_session)

    outcome = process.run_harness_process(plan, harness_registry)

    assert captured["fork_source_session"] == "source-session"
    assert captured["build_continue_session"] == "forked-session"
    assert captured["command_session"] == "forked-session"
    assert captured["chat_id_arg"] is None
    assert captured["start_harness_session_id"] == "forked-session"
    assert captured["forked_from_chat_id"] == "c7"
    assert outcome.chat_id == "c999"
    events = [
        json.loads(line)
        for line in (plan.state_root / "spawns.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    finalize_events = [event for event in events if event.get("event") == "finalize"]
    assert len(finalize_events) == 1
    assert finalize_events[0]["origin"] == "launcher"


def _build_context_plan(prompt: str = "hello") -> PreparedSpawnPlan:
    return PreparedSpawnPlan(
        model="gpt-5.4",
        harness_id=HarnessId.CODEX.value,
        prompt=prompt,
        agent_name=None,
        skills=(),
        skill_paths=(),
        reference_files=(),
        template_vars={},
        mcp_tools=(),
        session_agent="",
        session_agent_path="",
        session=SessionContinuation(),
        execution=ExecutionPolicy(
            permission_config=PermissionConfig(),
            permission_resolver=TieredPermissionResolver(config=PermissionConfig()),
        ),
        cli_command=(),
    )


def _deterministic_launch_tuple(
    ctx: LaunchContext,
) -> tuple[object, object, object, dict[str, str]]:
    return (
        ctx.run_params,
        ctx.spec,
        ctx.child_cwd,
        dict(ctx.env_overrides),
    )


def _build_context_run(plan: PreparedSpawnPlan, spawn_id: str = "p-ctx") -> Spawn:
    return Spawn(
        spawn_id=SpawnId(spawn_id),
        prompt=plan.prompt,
        model=ModelId(plan.model),
        status="queued",
    )


def test_prepare_launch_context_is_deterministic_and_immutable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    monkeypatch.setenv("MERIDIAN_CHAT_ID", "c-parent")
    monkeypatch.setenv("MERIDIAN_FS_DIR", str(tmp_path / ".meridian" / "fs"))
    monkeypatch.setenv("MERIDIAN_WORK_DIR", str(tmp_path / ".meridian" / "work"))

    adapter = CodexAdapter()
    plan = _build_context_plan()
    report_path = tmp_path / "report.md"
    plan_overrides = {"CUSTOM_TOOL_HOME": "/tmp/tool"}

    ctx_a = prepare_launch_context(
        spawn_id="p-ctx",
        run_prompt=plan.prompt,
        run_model=plan.model,
        plan=plan,
        harness=adapter,
        execution_cwd=tmp_path,
        state_root=tmp_path / ".meridian",
        plan_overrides=plan_overrides,
        report_output_path=report_path,
    )
    ctx_b = prepare_launch_context(
        spawn_id="p-ctx",
        run_prompt=plan.prompt,
        run_model=plan.model,
        plan=plan,
        harness=adapter,
        execution_cwd=tmp_path,
        state_root=tmp_path / ".meridian",
        plan_overrides=plan_overrides,
        report_output_path=report_path,
    )

    # Intentionally compare only the deterministic subset. `env` depends on the
    # ambient host environment and is not stable across runners or machines.
    assert _deterministic_launch_tuple(ctx_a) == _deterministic_launch_tuple(ctx_b)

    assert ctx_a.env_overrides["MERIDIAN_DEPTH"] == "2"
    assert ctx_a.env_overrides["MERIDIAN_CHAT_ID"] == "c-parent"
    assert ctx_a.env_overrides["CUSTOM_TOOL_HOME"] == "/tmp/tool"
    assert ctx_a.env["CUSTOM_TOOL_HOME"] == "/tmp/tool"
    assert isinstance(ctx_a.env, MappingProxyType)
    assert isinstance(ctx_a.env_overrides, MappingProxyType)

    with pytest.raises(TypeError):
        ctx_a.env["NEW_KEY"] = "value"  # type: ignore[index]
    with pytest.raises(TypeError):
        ctx_a.env_overrides["NEW_KEY"] = "value"  # type: ignore[index]


def test_prepare_launch_context_changes_deterministic_tuple_when_inputs_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")

    adapter = CodexAdapter()
    base_plan = _build_context_plan()
    fork_plan = base_plan.model_copy(
        update={
            "session": SessionContinuation(
                harness_session_id="session-123",
                continue_fork=True,
            )
        }
    )
    report_path = tmp_path / "report.md"

    base_ctx = prepare_launch_context(
        spawn_id="p-ctx",
        run_prompt=base_plan.prompt,
        run_model=base_plan.model,
        plan=base_plan,
        harness=adapter,
        execution_cwd=tmp_path,
        state_root=tmp_path / ".meridian",
        plan_overrides={},
        report_output_path=report_path,
    )
    fork_ctx = prepare_launch_context(
        spawn_id="p-ctx",
        run_prompt=fork_plan.prompt,
        run_model=fork_plan.model,
        plan=fork_plan,
        harness=adapter,
        execution_cwd=tmp_path,
        state_root=tmp_path / ".meridian",
        plan_overrides={},
        report_output_path=report_path,
    )

    assert _deterministic_launch_tuple(base_ctx) != _deterministic_launch_tuple(fork_ctx)


def test_prepare_launch_context_runtime_work_id_override_sets_work_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    monkeypatch.setenv("MERIDIAN_CHAT_ID", "c-parent")

    adapter = CodexAdapter()
    plan = _build_context_plan()
    state_root = tmp_path / ".meridian"
    ctx = prepare_launch_context(
        spawn_id="p-ctx",
        run_prompt=plan.prompt,
        run_model=plan.model,
        plan=plan,
        harness=adapter,
        execution_cwd=tmp_path,
        state_root=state_root,
        plan_overrides={},
        report_output_path=tmp_path / "report.md",
        runtime_work_id="fix-work-dir-export",
    )

    assert ctx.env_overrides["MERIDIAN_WORK_ID"] == "fix-work-dir-export"
    assert ctx.env_overrides["MERIDIAN_WORK_DIR"] == (
        state_root / "work" / "fix-work-dir-export"
    ).as_posix()


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

    runner_source = (source_root / "meridian/lib/launch/runner.py").read_text(encoding="utf-8")
    streaming_source = (
        source_root / "meridian/lib/launch/streaming_runner.py"
    ).read_text(encoding="utf-8")
    assert "DEFAULT_INFRA_EXIT_CODE =" not in runner_source
    assert "DEFAULT_INFRA_EXIT_CODE =" not in streaming_source
    assert DEFAULT_INFRA_EXIT_CODE == 2
