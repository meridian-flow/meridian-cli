"""Process management for primary agent launch."""

import logging
import os
import signal
import struct
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.spawn_lifecycle import (
    has_durable_report_completion,
    resolve_execution_terminal_state,
)
from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.claude_preflight import ensure_claude_session_accessible
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import LocalStore, make_artifact_key
from meridian.lib.state.paths import resolve_spawn_log_dir
from meridian.lib.state.session_store import (
    get_session_active_work_id,
    start_session,
    stop_session,
    update_session_harness_id,
    update_session_work_id,
)
from meridian.lib.state.spawn_store import FOREGROUND_LAUNCH_MODE

from .context import LaunchContext, build_launch_context
from .fork import materialize_fork
from .request import LaunchCompositionSurface, SpawnRequest
from .session_scope import session_scope
from .types import PrimarySessionMetadata, SessionMode

logger = logging.getLogger(__name__)
_PRIMARY_OUTPUT_FILENAME = "output.jsonl"


class _DeferredUnixModule:
    """Lazy module proxy so Unix-only modules load only on demand."""

    def __init__(self, module_name: str) -> None:
        self._module_name = module_name
        self._module: Any | None = None

    def _resolve(self) -> Any:
        if self._module is None:
            self._module = import_module(self._module_name)
        return self._module

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resolve(), name)


fcntl = _DeferredUnixModule("fcntl")
termios = _DeferredUnixModule("termios")


class ProcessOutcome(BaseModel):
    """Result of running the harness subprocess."""

    model_config = ConfigDict(frozen=True)

    command: tuple[str, ...]
    exit_code: int
    chat_id: str | None
    primary_spawn_id: str | None
    primary_started: float
    primary_started_epoch: float
    primary_started_local_iso: str | None
    resolved_harness_session_id: str


def _build_session_metadata(request: SpawnRequest) -> PrimarySessionMetadata:
    return PrimarySessionMetadata(
        harness=request.harness or "",
        model=request.model or "",
        agent=request.agent or "",
        agent_path=request.agent_metadata.get("session_agent_path") or "",
        skills=request.skills,
        skill_paths=request.skill_paths,
    )


def _resolve_primary_session_mode(context: LaunchContext) -> SessionMode:
    raw_mode = (context.resolved_request.session.primary_session_mode or "").strip()
    if not raw_mode:
        return SessionMode.FRESH
    try:
        return SessionMode(raw_mode)
    except ValueError:
        return SessionMode.FRESH


def _copy_primary_pty_output(
    *,
    child_pid: int,
    master_fd: int,
    output_log_path: Path,
) -> int:
    import select
    import termios
    import tty

    stdin_fd = sys.stdin.fileno()
    stdout_fd = sys.stdout.fileno()
    stdin_open = True
    saved_tty_attrs: Any = None

    output_log_path.parent.mkdir(parents=True, exist_ok=True)
    restore_resize = _install_winsize_forwarding(source_fd=stdout_fd, target_fd=master_fd)
    try:
        if os.isatty(stdin_fd):
            saved_tty_attrs = termios.tcgetattr(stdin_fd)
            tty.setraw(stdin_fd)

        with output_log_path.open("wb") as output_handle:
            while True:
                fds = [master_fd]
                if stdin_open:
                    fds.append(stdin_fd)
                ready, _, _ = select.select(fds, [], [])

                if master_fd in ready:
                    try:
                        chunk = os.read(master_fd, 4096)
                    except OSError:
                        chunk = b""
                    if not chunk:
                        break
                    output_handle.write(chunk)
                    output_handle.flush()
                    os.write(stdout_fd, chunk)

                if stdin_open and stdin_fd in ready:
                    data = os.read(stdin_fd, 1024)
                    if not data:
                        stdin_open = False
                    else:
                        os.write(master_fd, data)
    finally:
        restore_resize()
        if saved_tty_attrs is not None:
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, saved_tty_attrs)

    _, status = os.waitpid(child_pid, 0)
    return os.waitstatus_to_exitcode(status)


def _run_primary_process_with_capture(
    *,
    command: tuple[str, ...],
    cwd: Path,
    env: dict[str, str],
    output_log_path: Path | None,
    on_child_started: Callable[[int], None] | None = None,
) -> tuple[int, int | None]:
    if output_log_path is None or not sys.stdin.isatty() or not sys.stdout.isatty():
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            text=True,
        )
        if on_child_started is not None:
            try:
                on_child_started(process.pid)
            except Exception:
                if process.poll() is None:
                    process.terminate()
                    process.wait()
                raise
        try:
            return process.wait(), process.pid
        except KeyboardInterrupt:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                return process.wait(), process.pid
            return 130, process.pid

    # Create PTY and set correct size BEFORE forking, so child sees correct
    # terminal dimensions from the start.
    import pty

    master_fd, slave_fd = pty.openpty()
    _sync_pty_winsize(source_fd=sys.stdout.fileno(), target_fd=master_fd)

    child_pid = os.fork()
    if child_pid == 0:
        try:
            os.close(master_fd)
            os.setsid()
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            os.chdir(cwd)
            os.execvpe(command[0], command, env)
        except FileNotFoundError:
            os._exit(127)
        except Exception:
            os._exit(1)

    os.close(slave_fd)
    try:
        if on_child_started is not None:
            try:
                on_child_started(child_pid)
            except Exception:
                with suppress(ProcessLookupError):
                    os.kill(child_pid, signal.SIGTERM)
                with suppress(ChildProcessError):
                    os.waitpid(child_pid, 0)
                raise
        exit_code = _copy_primary_pty_output(
            child_pid=child_pid,
            master_fd=master_fd,
            output_log_path=output_log_path,
        )
        return exit_code, child_pid
    finally:
        with suppress(OSError):
            os.close(master_fd)


def _read_winsize(fd: int) -> bytes | None:
    """Return packed winsize bytes for one terminal fd, or None if unavailable."""

    try:
        return fcntl.ioctl(fd, termios.TIOCGWINSZ, struct.pack("HHHH", 0, 0, 0, 0))
    except OSError:
        return None


def _sync_pty_winsize(*, source_fd: int, target_fd: int) -> None:
    """Copy the current terminal winsize onto the PTY master."""

    winsize = _read_winsize(source_fd)
    if winsize is None:
        return
    try:
        fcntl.ioctl(target_fd, termios.TIOCSWINSZ, winsize)
    except OSError:
        return


def _invoke_previous_sigwinch_handler(
    previous: signal.Handlers,
    *,
    signum: int,
    frame: Any,
) -> None:
    if previous in {signal.SIG_DFL, signal.SIG_IGN, None}:
        return
    if callable(previous):
        previous(signum, frame)


def _install_winsize_forwarding(*, source_fd: int, target_fd: int) -> Any:
    """Sync PTY size now and on future terminal resize signals."""

    _sync_pty_winsize(source_fd=source_fd, target_fd=target_fd)
    previous = cast("signal.Handlers", signal.getsignal(signal.SIGWINCH))

    def _handle_resize(signum: int, frame: Any) -> None:
        _sync_pty_winsize(source_fd=source_fd, target_fd=target_fd)
        _invoke_previous_sigwinch_handler(previous, signum=signum, frame=frame)

    signal.signal(signal.SIGWINCH, _handle_resize)

    def _restore() -> None:
        signal.signal(signal.SIGWINCH, previous)

    return _restore


def run_harness_process(
    launch_context: LaunchContext,
    harness_registry: HarnessRegistry,
) -> ProcessOutcome:
    """Start session, spawn tracking, launch process, wait for exit."""

    repo_root = launch_context.repo_root
    execution_cwd = launch_context.execution_cwd
    state_root = launch_context.state_root
    preview_context = launch_context
    command = preview_context.argv
    spawn_request = preview_context.request
    preview_request = preview_context.resolved_request
    session_mode = _resolve_primary_session_mode(preview_context)
    session_metadata = _build_session_metadata(preview_request)
    resolved_harness_session_id = preview_context.seed_harness_session_id or ""
    session_scope_harness_session_id = resolved_harness_session_id
    if session_mode == SessionMode.FORK:
        session_scope_harness_session_id = (
            (preview_request.session.requested_harness_session_id or "").strip()
            or session_scope_harness_session_id
        )
    harness_adapter = preview_context.harness
    harness_id = HarnessId(session_metadata.harness)
    chat_id: str | None = None
    primary_spawn_id: SpawnId | None = None
    primary_started = 0.0
    primary_started_epoch = 0.0
    primary_started_local_iso: str | None = None
    artifacts = LocalStore(root_dir=state_root / "artifacts")

    resume_chat_id = (
        preview_request.session.continue_chat_id
        if session_mode == SessionMode.RESUME
        else None
    )
    exit_code = 2
    try:
        with session_scope(
            state_root=state_root,
            harness=session_metadata.harness,
            harness_session_id=session_scope_harness_session_id,
            model=session_metadata.model,
            chat_id=resume_chat_id,
            forked_from_chat_id=preview_request.session.forked_from_chat_id,
            agent=session_metadata.agent,
            agent_path=session_metadata.agent_path,
            skills=session_metadata.skills,
            skill_paths=session_metadata.skill_paths,
            execution_cwd=str(execution_cwd),
            kind="primary",
            _start_session=start_session,
            _stop_session=stop_session,
            _update_session_harness_id=update_session_harness_id,
        ) as managed:
            chat_id = managed.chat_id
            explicit_work_id = preview_context.work_id
            preserved_work_id = None
            if explicit_work_id is None and resume_chat_id is not None:
                preserved_work_id = get_session_active_work_id(
                    state_root,
                    resume_chat_id,
                )
            attached_work_id = get_session_active_work_id(state_root, chat_id)
            if attached_work_id is None:
                attached_work_id = explicit_work_id or preserved_work_id
                if attached_work_id is not None:
                    update_session_work_id(state_root, chat_id, attached_work_id)
            try:
                # I-10: do NOT pre-populate harness_session_id on fork starts.
                # The forked session ID is unknown until materialize_fork() runs
                # after the row exists.
                should_fork = (
                    session_mode == SessionMode.FORK
                    and harness_id == HarnessId.CODEX
                    and bool(
                        (preview_request.session.requested_harness_session_id or "").strip()
                    )
                )
                primary_spawn_id = spawn_store.start_spawn(
                    state_root,
                    chat_id=chat_id,
                    model=session_metadata.model,
                    agent=session_metadata.agent,
                    agent_path=session_metadata.agent_path or None,
                    skills=session_metadata.skills,
                    skill_paths=session_metadata.skill_paths,
                    harness=session_metadata.harness,
                    kind="primary",
                    prompt=preview_request.prompt,
                    harness_session_id=None if should_fork else resolved_harness_session_id,
                    execution_cwd=str(execution_cwd),
                    launch_mode=FOREGROUND_LAUNCH_MODE,
                    work_id=attached_work_id,
                    runner_pid=os.getpid(),
                    status="queued",
                )
                # I-10: fork row exists now — safe to call fork_session via sole owner.
                if should_fork:
                    source_session_id = (
                        preview_request.session.requested_harness_session_id or ""
                    ).strip()
                    forked_session_id = materialize_fork(
                        adapter=harness_adapter,
                        source_session_id=source_session_id,
                        state_root=state_root,
                        spawn_id=primary_spawn_id,
                    )
                    spawn_request = spawn_request.model_copy(
                        update={
                            "session": spawn_request.session.model_copy(
                                update={
                                    "requested_harness_session_id": forked_session_id,
                                    "continue_fork": False,
                                }
                            )
                        }
                    )
                    resolved_harness_session_id = forked_session_id
                log_dir = resolve_spawn_log_dir(repo_root, primary_spawn_id)
                primary_started = time.monotonic()
                primary_started_epoch = time.time()
                primary_started_local_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                runtime_request = spawn_request.model_copy(
                    update={"work_id_hint": attached_work_id}
                )
                runtime = preview_context.runtime.model_copy(
                    update={
                        "composition_surface": LaunchCompositionSurface.PRIMARY,
                        "state_root": state_root.as_posix(),
                        "project_paths_repo_root": repo_root.as_posix(),
                        "project_paths_execution_cwd": execution_cwd.as_posix(),
                        "report_output_path": (log_dir / "report.md").as_posix(),
                    }
                )
                plan_overrides: dict[str, str] = {}
                if runtime_request.autocompact is not None:
                    plan_overrides["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] = str(
                        runtime_request.autocompact
                    )
                runtime_context = build_launch_context(
                    spawn_id=str(primary_spawn_id),
                    request=runtime_request,
                    runtime=runtime,
                    harness_registry=harness_registry,
                    plan_overrides=plan_overrides,
                    runtime_work_id=attached_work_id,
                )
                command = runtime_context.argv
                resolved_harness_session_id = runtime_context.seed_harness_session_id or ""
                child_env = dict(runtime_context.env)
                # Primary launches own the session created by session_scope().
                # Ensure the harness process gets that chat id even when no
                # parent MERIDIAN_CHAT_ID exists in the launcher environment.
                if managed.chat_id:
                    child_env["MERIDIAN_CHAT_ID"] = managed.chat_id
                child_cwd = runtime_context.child_cwd
                output_log_path = log_dir / _PRIMARY_OUTPUT_FILENAME

                # Symlink source session for primary fork launches.
                if (
                    harness_adapter.id == HarnessId.CLAUDE
                    and preview_request.session.source_execution_cwd
                    and resolved_harness_session_id
                ):
                    ensure_claude_session_accessible(
                        source_session_id=resolved_harness_session_id,
                        source_cwd=Path(preview_request.session.source_execution_cwd),
                        child_cwd=child_cwd,
                    )

                def _record_primary_started(child_pid: int) -> None:
                    spawn_store.mark_spawn_running(
                        state_root,
                        primary_spawn_id,
                        launch_mode=FOREGROUND_LAUNCH_MODE,
                        worker_pid=child_pid,
                    )

                exit_code, _child_pid = _run_primary_process_with_capture(
                    command=command,
                    cwd=child_cwd,
                    env=child_env,
                    output_log_path=output_log_path,
                    on_child_started=_record_primary_started,
                )
                with suppress(Exception):
                    spawn_store.record_spawn_exited(
                        state_root,
                        primary_spawn_id,
                        exit_code=exit_code,
                    )
                if output_log_path.exists():
                    artifacts.put(
                        make_artifact_key(primary_spawn_id, _PRIMARY_OUTPUT_FILENAME),
                        output_log_path.read_bytes(),
                    )
            finally:
                durable_report = False
                terminated_after_completion = False
                if primary_spawn_id is not None:
                    report_path = resolve_spawn_log_dir(repo_root, primary_spawn_id) / "report.md"
                    try:
                        report_text = (
                            report_path.read_text(encoding="utf-8")
                            if report_path.is_file()
                            else None
                        )
                    except OSError:
                        report_text = None
                    durable_report = has_durable_report_completion(report_text)
                    terminated_after_completion = durable_report and exit_code in (143, -15)
                status, exit_code, _failure_reason = resolve_execution_terminal_state(
                    exit_code=exit_code,
                    failure_reason=None,
                    cancelled=False,
                    durable_report_completion=durable_report,
                    terminated_after_completion=terminated_after_completion,
                )
                if primary_spawn_id is not None:
                    duration = (
                        max(0.0, time.monotonic() - primary_started)
                        if primary_started > 0.0
                        else None
                    )
                    spawn_store.finalize_spawn(
                        state_root,
                        primary_spawn_id,
                        status=status,
                        exit_code=exit_code,
                        origin="launcher",
                        duration_secs=duration,
                    )
                try:
                    observed_harness_session_id = None
                    if primary_started_epoch > 0.0:
                        # I-4: observe_session_id() is the sole observation callsite.
                        observed_harness_session_id = harness_adapter.observe_session_id(
                            artifacts=artifacts,
                            spawn_id=primary_spawn_id,
                            current_session_id=resolved_harness_session_id,
                            repo_root=repo_root,
                            started_at_epoch=primary_started_epoch,
                            started_at_local_iso=primary_started_local_iso,
                        )
                    if (
                        observed_harness_session_id is not None
                        and observed_harness_session_id.strip()
                        and observed_harness_session_id.strip()
                        != resolved_harness_session_id.strip()
                    ):
                        resolved_harness_session_id = observed_harness_session_id.strip()
                        managed.record_harness_session_id(resolved_harness_session_id)
                        if primary_spawn_id is not None:
                            spawn_store.update_spawn(
                                state_root,
                                primary_spawn_id,
                                harness_session_id=resolved_harness_session_id,
                            )
                except Exception:
                    logger.debug(
                        "Best-effort harness session persistence failed",
                        exc_info=True,
                    )
    except FileNotFoundError:
        logger.debug("Harness command not found", exc_info=True)
        exit_code = 2

    return ProcessOutcome(
        command=command,
        exit_code=exit_code,
        chat_id=chat_id,
        primary_spawn_id=primary_spawn_id,
        primary_started=primary_started,
        primary_started_epoch=primary_started_epoch,
        primary_started_local_iso=primary_started_local_iso,
        resolved_harness_session_id=resolved_harness_session_id,
    )


__all__ = [
    "ProcessOutcome",
    "run_harness_process",
]
