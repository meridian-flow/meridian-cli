"""Execution engine primitives."""

from meridian.lib.exec.errors import ErrorCategory, classify_error, should_retry
from meridian.lib.exec.signals import map_process_exit_code, signal_to_exit_code
from meridian.lib.exec.spawn import (
    SafeDefaultPermissionResolver,
    SpawnResult,
    execute_with_finalization,
    run_log_dir,
    spawn_and_stream,
)
from meridian.lib.exec.timeout import (
    DEFAULT_KILL_GRACE_SECONDS,
    SpawnTimeoutError,
    terminate_process,
    wait_for_process_exit,
)

__all__ = [
    "DEFAULT_KILL_GRACE_SECONDS",
    "ErrorCategory",
    "SpawnTimeoutError",
    "SafeDefaultPermissionResolver",
    "SpawnResult",
    "classify_error",
    "execute_with_finalization",
    "map_process_exit_code",
    "run_log_dir",
    "should_retry",
    "signal_to_exit_code",
    "spawn_and_stream",
    "terminate_process",
    "wait_for_process_exit",
]
