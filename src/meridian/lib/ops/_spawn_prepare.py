"""Compatibility shim for moved spawn preparation helpers."""

from __future__ import annotations

import sys

from .spawn import prepare as _impl

sys.modules[__name__] = _impl
