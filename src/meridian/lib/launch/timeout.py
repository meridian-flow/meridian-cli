"""Timeout helpers for subprocess execution."""

import asyncio
import signal

from meridian.lib.config.settings import MeridianConfig

from .signals import signal_process_group

DEFAULT_KILL_GRACE_SECONDS = MeridianConfig().kill_grace_minutes * 60.0


class SpawnTimeoutError(TimeoutError):
    """Raised when a harness process exceeds the configured timeout."""

    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Spawn exceeded timeout after {timeout_seconds:.3f}s")


async def wait_for_process_returncode(
    process: asyncio.subprocess.Process,
    *,
    timeout_seconds: float | None = None,
    poll_interval_seconds: float = 0.05,
) -> int:
    """Wait until the subprocess exit status is available.

    This intentionally polls ``process.returncode`` instead of awaiting
    ``process.wait()`` because asyncio may delay ``wait()`` completion until
    stdout/stderr transports disconnect, which can be held open by descendants
    that inherited the harness pipes.
    """

    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be > 0 when provided.")

    deadline = (
        None if timeout_seconds is None else asyncio.get_running_loop().time() + timeout_seconds
    )
    while process.returncode is None:
        if deadline is not None and asyncio.get_running_loop().time() >= deadline:
            assert timeout_seconds is not None
            raise SpawnTimeoutError(timeout_seconds)
        await asyncio.sleep(poll_interval_seconds)
    return process.returncode


async def terminate_process(
    process: asyncio.subprocess.Process,
    *,
    grace_seconds: float = DEFAULT_KILL_GRACE_SECONDS,
) -> None:
    """Gracefully terminate a process and force-kill if it does not exit."""

    if process.returncode is not None:
        return

    # Timeout expiry is an infra-enforced deadline (not a user interrupt),
    # so we begin with SIGTERM and only escalate to SIGKILL after grace.
    signal_process_group(process, signal.SIGTERM)
    try:
        await wait_for_process_returncode(process, timeout_seconds=grace_seconds)
    except SpawnTimeoutError:
        if process.returncode is None:
            signal_process_group(process, signal.SIGKILL)
            await wait_for_process_returncode(process)


async def wait_for_process_exit(
    process: asyncio.subprocess.Process,
    *,
    timeout_seconds: float | None,
    kill_grace_seconds: float = DEFAULT_KILL_GRACE_SECONDS,
) -> int:
    """Wait for process completion with timeout-triggered termination."""

    if timeout_seconds is None:
        return await wait_for_process_returncode(process)

    try:
        return await wait_for_process_returncode(process, timeout_seconds=timeout_seconds)
    except SpawnTimeoutError as exc:
        await terminate_process(process, grace_seconds=kill_grace_seconds)
        raise SpawnTimeoutError(timeout_seconds) from exc
