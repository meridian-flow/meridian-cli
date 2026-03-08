"""Compatibility shim for moved spawn models."""

from __future__ import annotations

import sys

from .spawn import models as _impl

sys.modules[__name__] = _impl
