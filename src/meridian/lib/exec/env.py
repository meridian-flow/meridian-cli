"""Re-export shim for backward compatibility."""

from __future__ import annotations

import sys

from meridian.lib.launch.env import (
    HARNESS_ENV_PASS_THROUGH,
    build_harness_child_env,
    build_harness_env_overrides,
    sanitize_child_env,
)
from meridian.lib.launch import env as _env

__all__ = [
    "HARNESS_ENV_PASS_THROUGH",
    "build_harness_child_env",
    "build_harness_env_overrides",
    "sanitize_child_env",
]

sys.modules[__name__] = _env
