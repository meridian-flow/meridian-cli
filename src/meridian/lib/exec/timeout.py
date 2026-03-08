"""Re-export shim for backward compatibility."""

from __future__ import annotations

import sys

from meridian.lib.launch.timeout import (
    DEFAULT_KILL_GRACE_SECONDS,
    SpawnTimeoutError,
    terminate_process,
    wait_for_process_exit,
)
from meridian.lib.launch import timeout as _timeout

__all__ = [
    "DEFAULT_KILL_GRACE_SECONDS",
    "SpawnTimeoutError",
    "terminate_process",
    "wait_for_process_exit",
]

sys.modules[__name__] = _timeout
