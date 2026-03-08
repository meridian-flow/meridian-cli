"""Compatibility shim for prompt hygiene helpers."""

from meridian.lib.launch.prompt import sanitize_prior_output, strip_stale_report_paths

__all__ = ["sanitize_prior_output", "strip_stale_report_paths"]
