"""Timeout helpers for subprocess execution."""

from __future__ import annotations

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
        await asyncio.wait_for(process.wait(), timeout=grace_seconds)
    except TimeoutError:
        if process.returncode is None:
            signal_process_group(process, signal.SIGKILL)
            await process.wait()


async def wait_for_process_exit(
    process: asyncio.subprocess.Process,
    *,
    timeout_seconds: float | None,
    kill_grace_seconds: float = DEFAULT_KILL_GRACE_SECONDS,
) -> int:
    """Wait for process completion with timeout-triggered termination."""

    if timeout_seconds is None:
        return await process.wait()

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be > 0 when provided.")

    try:
        return await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
    except TimeoutError as exc:
        await terminate_process(process, grace_seconds=kill_grace_seconds)
        raise SpawnTimeoutError(timeout_seconds) from exc
