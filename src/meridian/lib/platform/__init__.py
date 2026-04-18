"""Platform detection constants for cross-platform code."""

from __future__ import annotations

import sys

IS_WINDOWS = sys.platform == "win32"
IS_POSIX = not IS_WINDOWS

__all__ = ["IS_POSIX", "IS_WINDOWS"]
