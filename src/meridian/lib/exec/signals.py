"""Re-export shim for backward compatibility."""

from __future__ import annotations

import sys

from meridian.lib.launch.signals import (
    TARGET_SIGNALS,
    SignalCoordinator,
    SignalForwarder,
    map_process_exit_code,
    signal_coordinator,
    signal_process_group,
    signal_to_exit_code,
)
from meridian.lib.launch import signals as _signals

__all__ = [
    "TARGET_SIGNALS",
    "SignalCoordinator",
    "SignalForwarder",
    "map_process_exit_code",
    "signal_coordinator",
    "signal_process_group",
    "signal_to_exit_code",
]

sys.modules[__name__] = _signals
