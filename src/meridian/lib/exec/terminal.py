"""Re-export shim for backward compatibility."""

from __future__ import annotations

import sys

from meridian.lib.launch.terminal import (
    ALL_EVENT_CATEGORIES,
    DEFAULT_VISIBLE_CATEGORIES,
    QUIET_VISIBLE_CATEGORIES,
    VERBOSE_VISIBLE_CATEGORIES,
    TerminalEventFilter,
    format_stderr_for_terminal,
    resolve_visible_categories,
    summarize_stderr,
)
from meridian.lib.launch import terminal as _terminal

__all__ = [
    "ALL_EVENT_CATEGORIES",
    "DEFAULT_VISIBLE_CATEGORIES",
    "QUIET_VISIBLE_CATEGORIES",
    "VERBOSE_VISIBLE_CATEGORIES",
    "TerminalEventFilter",
    "format_stderr_for_terminal",
    "resolve_visible_categories",
    "summarize_stderr",
]

sys.modules[__name__] = _terminal
