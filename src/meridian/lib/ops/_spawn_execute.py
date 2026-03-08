"""Compatibility shim for moved spawn execution helpers."""

from __future__ import annotations

import sys

from .spawn import execute as _impl

if __name__ == "__main__":
    raise SystemExit(getattr(_impl, "_background_worker_main")())

sys.modules[__name__] = _impl
