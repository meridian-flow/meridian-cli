"""Compatibility shim for moved spawn query helpers."""

from __future__ import annotations

import sys

from .spawn import query as _impl

sys.modules[__name__] = _impl
