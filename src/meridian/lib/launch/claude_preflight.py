"""Backward-compatible Claude preflight exports.

Phase 3 moved adapter-owned preflight helpers to
``meridian.lib.harness.claude_preflight``.
"""

from meridian.lib.harness.claude_preflight import (
    CLAUDE_PARENT_ALLOWED_TOOLS_FLAG,
    ensure_claude_session_accessible,
    expand_claude_passthrough_args,
    project_slug,
    read_parent_claude_permissions,
)
from meridian.lib.launch.text_utils import merge_allowed_tools_flag

__all__ = [
    "CLAUDE_PARENT_ALLOWED_TOOLS_FLAG",
    "ensure_claude_session_accessible",
    "expand_claude_passthrough_args",
    "merge_allowed_tools_flag",
    "project_slug",
    "read_parent_claude_permissions",
]
