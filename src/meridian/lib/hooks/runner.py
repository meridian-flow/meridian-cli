"""External hook execution primitives."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

import psutil

from meridian.lib.hooks.types import Hook, HookContext, HookResult

_TAIL_BYTES = 1024
_TERM_GRACE_SECONDS = 2.0
_HOOKS_ENABLED_ENV = "MERIDIAN_HOOKS_ENABLED"


def hooks_dispatch_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return whether hook dispatch should run globally."""

    scope = os.environ if env is None else env
    value = scope.get(_HOOKS_ENABLED_ENV)
    if value is None:
        return True
    return value.strip().lower() != "false"


def _tail_text(data: bytes | None) -> str | None:
    if not data:
        return None
    return data[-_TAIL_BYTES:].decode("utf-8", errors="replace")


def _as_bytes(data: bytes | str | None) -> bytes:
    if data is None:
        return b""
    if isinstance(data, bytes):
        return data
    return data.encode("utf-8", errors="replace")


def _terminate_process_tree(process: subprocess.Popen[bytes], *, grace_secs: float) -> None:
    """Terminate a hook subprocess and descendants before draining pipes."""

    poll = getattr(process, "poll", None)
    if callable(poll) and poll() is not None:
        return

    pid = getattr(process, "pid", None)
    if not isinstance(pid, int):
        process.terminate()
        return

    try:
        root = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return

    children: list[psutil.Process] = []
    with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
        children = root.children(recursive=True)
    tree = [*children, root]

    for proc in tree:
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            proc.terminate()

    _, alive = psutil.wait_procs(tree, timeout=grace_secs)
    if not alive:
        return

    for proc in alive:
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            proc.kill()

    psutil.wait_procs(alive, timeout=1.0)


class ExternalHookRunner:
    """Run one external hook command with context transport and timeout handling."""

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.expanduser().resolve()

    def run(self, hook: Hook, context: HookContext, *, timeout_secs: int) -> HookResult:
        """Execute one hook command and return structured result."""

        if not hooks_dispatch_enabled():
            return HookResult(
                hook_name=hook.name,
                event=context.event_name,
                outcome="skipped",
                success=True,
                skipped=True,
                skip_reason="hooks_disabled",
            )

        if timeout_secs <= 0:
            raise ValueError("timeout_secs must be > 0.")

        if not hook.command:
            return HookResult(
                hook_name=hook.name,
                event=context.event_name,
                outcome="failure",
                success=False,
                error="Hook command is required for external execution.",
            )

        env = {**os.environ, **context.to_env()}
        start = time.monotonic()
        process: subprocess.Popen[bytes] | None = None

        try:
            process = subprocess.Popen(
                hook.command,
                shell=True,
                cwd=self._project_root,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = process.communicate(
                input=context.to_json().encode("utf-8"),
                timeout=timeout_secs,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            if process.returncode == 0:
                return HookResult(
                    hook_name=hook.name,
                    event=context.event_name,
                    outcome="success",
                    success=True,
                    exit_code=0,
                    duration_ms=duration_ms,
                    stdout=_tail_text(stdout),
                    stderr=_tail_text(stderr),
                )
            return HookResult(
                hook_name=hook.name,
                event=context.event_name,
                outcome="failure",
                success=False,
                error=f"Exited with code {process.returncode}.",
                exit_code=process.returncode,
                duration_ms=duration_ms,
                stdout=_tail_text(stdout),
                stderr=_tail_text(stderr),
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _as_bytes(exc.stdout)
            stderr = _as_bytes(exc.stderr)

            if process is not None:
                _terminate_process_tree(process, grace_secs=_TERM_GRACE_SECONDS)
                try:
                    term_stdout, term_stderr = process.communicate(timeout=1.0)
                except subprocess.TimeoutExpired as kill_exc:
                    stdout += _as_bytes(kill_exc.stdout)
                    stderr += _as_bytes(kill_exc.stderr)
                    process.kill()
                    kill_stdout, kill_stderr = process.communicate()
                    stdout += kill_stdout
                    stderr += kill_stderr
                else:
                    stdout += term_stdout
                    stderr += term_stderr

            return HookResult(
                hook_name=hook.name,
                event=context.event_name,
                outcome="timeout",
                success=False,
                error=f"Timed out after {timeout_secs}s.",
                exit_code=None if process is None else process.returncode,
                duration_ms=int((time.monotonic() - start) * 1000),
                stdout=_tail_text(stdout),
                stderr=_tail_text(stderr),
            )
        except OSError as exc:
            return HookResult(
                hook_name=hook.name,
                event=context.event_name,
                outcome="failure",
                success=False,
                error=str(exc),
                duration_ms=int((time.monotonic() - start) * 1000),
            )
