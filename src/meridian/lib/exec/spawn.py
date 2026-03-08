"""Re-export shim for backward compatibility."""

from __future__ import annotations

import sys

from meridian.lib.launch.runner import (
    DEFAULT_GUARDRAIL_TIMEOUT_SECONDS,
    DEFAULT_INFRA_EXIT_CODE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BACKOFF_SECONDS,
    OUTPUT_FILENAME,
    REPORT_FILENAME,
    STDERR_FILENAME,
    TOKENS_FILENAME,
    SafeDefaultPermissionResolver,
    SpawnResult,
    execute_with_finalization,
    run_log_dir,
    sanitize_child_env,
    spawn_and_stream,
)
from meridian.lib.launch import runner as _runner

__all__ = [
    "DEFAULT_GUARDRAIL_TIMEOUT_SECONDS",
    "DEFAULT_INFRA_EXIT_CODE",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_RETRY_BACKOFF_SECONDS",
    "OUTPUT_FILENAME",
    "REPORT_FILENAME",
    "STDERR_FILENAME",
    "TOKENS_FILENAME",
    "SafeDefaultPermissionResolver",
    "SpawnResult",
    "execute_with_finalization",
    "run_log_dir",
    "sanitize_child_env",
    "spawn_and_stream",
]

sys.modules[__name__] = _runner
