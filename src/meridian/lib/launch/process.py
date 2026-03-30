"""Process management for primary agent launch."""

import fcntl
import logging
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import tty
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.spawn_lifecycle import (
    has_durable_report_completion,
    resolve_execution_terminal_state,
)
from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import LocalStore, make_artifact_key
from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.state.paths import resolve_spawn_log_dir, resolve_state_paths
from meridian.lib.state.session_store import (
    get_session_active_work_id,
    start_session,
    stop_session,
    update_session_harness_id,
    update_session_work_id,
)
from meridian.lib.state.spawn_store import FOREGROUND_LAUNCH_MODE

from .command import build_launch_env
from .heartbeat import threaded_heartbeat_scope
from .plan import ResolvedPrimaryLaunchPlan
from .runner import ensure_claude_session_accessible
from .session_ids import extract_latest_session_id
from .session_scope import session_scope
from .types import SessionMode

logger = logging.getLogger(__name__)
_PRIMARY_OUTPUT_FILENAME = "output.jsonl"


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


def _resolve_command_and_session(
    plan: ResolvedPrimaryLaunchPlan,
) -> tuple[tuple[str, ...], str, SpawnParams]:
    """Resolve command and effective harness session for this launch run."""

    command = plan.command
    resolved_harness_session_id = plan.seed_harness_session_id
    run_params = plan.run_params
    should_materialize_fork = (
        plan.request.session_mode == SessionMode.FORK
        and not plan.request.dry_run
        and plan.adapter.id == HarnessId.CODEX
        and bool((run_params.continue_harness_session_id or "").strip())
    )
    if not should_materialize_fork:
        return command, resolved_harness_session_id, run_params

    if plan.permission_resolver is None:
        raise RuntimeError("Missing permission resolver for fork launch command construction.")

    source_session_id = run_params.continue_harness_session_id or ""
    fork_session = cast("Callable[[str], str] | None", getattr(plan.adapter, "fork_session", None))
    if fork_session is None:
        raise RuntimeError("Harness adapter does not implement fork_session().")
    forked_session_id = fork_session(source_session_id).strip()
    if not forked_session_id:
        raise RuntimeError("Harness adapter returned empty fork session ID.")
    run_params = run_params.model_copy(
        update={
            "continue_harness_session_id": forked_session_id,
            # Codex forking is materialized before launch command build.
            "continue_fork": False,
        }
    )
    resolved_harness_session_id = forked_session_id
    command = tuple(plan.adapter.build_command(run_params, plan.permission_resolver))
    return command, resolved_harness_session_id, run_params


def _copy_primary_pty_output(
    *,
    child_pid: int,
    master_fd: int,
    output_log_path: Path,
) -> int:
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

    child_pid, master_fd = pty.fork()
    if child_pid == 0:
        try:
            os.chdir(cwd)
            os.execvpe(command[0], command, env)
        except FileNotFoundError:
            os._exit(127)
        except Exception:
            os._exit(1)

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
        _sync_pty_winsize(source_fd=sys.stdout.fileno(), target_fd=master_fd)
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
    plan: ResolvedPrimaryLaunchPlan,
    harness_registry: HarnessRegistry,
) -> ProcessOutcome:
    """Start session, spawn tracking, launch process, wait for exit."""

    repo_root = plan.repo_root
    command, resolved_harness_session_id, run_params = _resolve_command_and_session(plan)
    chat_id: str | None = None
    primary_spawn_id: SpawnId | None = None
    primary_started = 0.0
    primary_started_epoch = 0.0
    primary_started_local_iso: str | None = None
    artifacts = LocalStore(root_dir=resolve_state_paths(plan.repo_root).artifacts_dir)

    resume_chat_id = (
        plan.request.continue_chat_id if plan.request.session_mode == SessionMode.RESUME else None
    )
    exit_code = 2
    try:
        with session_scope(
            state_root=plan.state_root,
            harness=plan.session_metadata.harness,
            harness_session_id=resolved_harness_session_id,
            model=plan.session_metadata.model,
            chat_id=resume_chat_id,
            forked_from_chat_id=plan.request.forked_from_chat_id,
            agent=plan.session_metadata.agent,
            agent_path=plan.session_metadata.agent_path,
            agent_source=plan.session_metadata.agent_source,
            skills=plan.session_metadata.skills,
            skill_paths=plan.session_metadata.skill_paths,
            skill_sources=plan.session_metadata.skill_sources,
            bootstrap_required_items=plan.session_metadata.bootstrap_required_items,
            bootstrap_missing_items=plan.session_metadata.bootstrap_missing_items,
            execution_cwd=str(repo_root),
            _start_session=start_session,
            _stop_session=stop_session,
            _update_session_harness_id=update_session_harness_id,
        ) as managed:
            chat_id = managed.chat_id
            explicit_work_id = plan.resolved_work_id
            preserved_work_id = None
            if explicit_work_id is None and resume_chat_id is not None:
                preserved_work_id = get_session_active_work_id(
                    plan.state_root,
                    resume_chat_id,
                )
            attached_work_id = get_session_active_work_id(plan.state_root, chat_id)
            if attached_work_id is None:
                attached_work_id = explicit_work_id or preserved_work_id
                if attached_work_id is not None:
                    update_session_work_id(plan.state_root, chat_id, attached_work_id)
            try:
                primary_spawn_id = spawn_store.start_spawn(
                    plan.state_root,
                    chat_id=chat_id,
                    model=plan.session_metadata.model,
                    agent=plan.session_metadata.agent,
                    agent_path=plan.session_metadata.agent_path or None,
                    agent_source=plan.session_metadata.agent_source,
                    skills=plan.session_metadata.skills,
                    skill_paths=plan.session_metadata.skill_paths,
                    skill_sources=plan.session_metadata.skill_sources,
                    bootstrap_required_items=plan.session_metadata.bootstrap_required_items,
                    bootstrap_missing_items=plan.session_metadata.bootstrap_missing_items,
                    harness=plan.session_metadata.harness,
                    kind="primary",
                    prompt=plan.prompt,
                    harness_session_id=resolved_harness_session_id,
                    execution_cwd=str(repo_root),
                    launch_mode=FOREGROUND_LAUNCH_MODE,
                    work_id=attached_work_id,
                    status="queued",
                )
                log_dir = resolve_spawn_log_dir(repo_root, primary_spawn_id)
                with threaded_heartbeat_scope(log_dir / "heartbeat"):
                    primary_started = time.monotonic()
                    primary_started_epoch = time.time()
                    primary_started_local_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                    child_env = build_launch_env(
                        repo_root,
                        plan.request,
                        chat_id=chat_id,
                        work_id=attached_work_id,
                        default_autocompact_pct=plan.config.primary.autocompact_pct,
                        spawn_id=primary_spawn_id,
                        adapter=plan.adapter,
                        run_params=run_params,
                        permission_config=plan.permission_config,
                    )
                    output_log_path = log_dir / _PRIMARY_OUTPUT_FILENAME

                    # Symlink source session for primary fork launches.
                    if (
                        plan.adapter.id == HarnessId.CLAUDE
                        and plan.source_execution_cwd
                        and resolved_harness_session_id
                    ):
                        ensure_claude_session_accessible(
                            source_session_id=resolved_harness_session_id,
                            source_cwd=Path(plan.source_execution_cwd),
                            child_cwd=repo_root,
                        )

                    def _record_primary_started(child_pid: int) -> None:
                        atomic_write_text(
                            log_dir / "harness.pid",
                            f"{child_pid}\n",
                        )
                        spawn_store.mark_spawn_running(
                            plan.state_root,
                            primary_spawn_id,
                            launch_mode=FOREGROUND_LAUNCH_MODE,
                            worker_pid=child_pid,
                        )

                    exit_code, _child_pid = _run_primary_process_with_capture(
                        command=command,
                        cwd=repo_root,
                        env=child_env,
                        output_log_path=output_log_path,
                        on_child_started=_record_primary_started,
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
                        plan.state_root,
                        primary_spawn_id,
                        status=status,
                        exit_code=exit_code,
                        duration_secs=duration,
                    )
                try:
                    observed_harness_session_id = None
                    if primary_started_epoch > 0.0:
                        observed_harness_session_id = extract_latest_session_id(
                            adapter=plan.adapter,
                            current_session_id=resolved_harness_session_id,
                            artifacts=artifacts,
                            spawn_id=primary_spawn_id,
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
                                plan.state_root,
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
