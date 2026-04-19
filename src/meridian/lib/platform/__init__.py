"""Platform detection constants for cross-platform code."""

from __future__ import annotations

import sys

from .unix_modules import DeferredUnixModule, fcntl, pty, select, termios, tty

IS_WINDOWS = sys.platform == "win32"
IS_POSIX = not IS_WINDOWS

__all__ = [
    "DeferredUnixModule",
    "IS_POSIX",
    "IS_WINDOWS",
    "fcntl",
    "pty",
    "select",
    "termios",
    "tty",
]
