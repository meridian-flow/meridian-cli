"""Re-export shim for backward compatibility."""

from __future__ import annotations

import sys

from meridian.lib.launch.signals import signal_process_group
from meridian.lib.launch import signals as _signals

__all__ = ["signal_process_group"]

sys.modules[__name__] = _signals
