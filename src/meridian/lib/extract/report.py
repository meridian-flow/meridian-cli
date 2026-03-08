"""Compatibility shim for report extraction helpers."""

from meridian.lib.launch.report import (
    ExtractedReport,
    ReportSource,
    extract_or_fallback_report,
)

__all__ = [
    "ExtractedReport",
    "ReportSource",
    "extract_or_fallback_report",
]
