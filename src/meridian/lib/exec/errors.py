"""Re-export shim for backward compatibility."""

from __future__ import annotations

import sys

from meridian.lib.launch.errors import ErrorCategory, classify_error, should_retry
from meridian.lib.launch import errors as _errors

__all__ = ["ErrorCategory", "classify_error", "should_retry"]

sys.modules[__name__] = _errors
