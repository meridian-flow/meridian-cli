"""Shared CWD resolution for child spawn processes."""

import os
from pathlib import Path

from meridian.lib.core.types import HarnessId
from meridian.lib.state.paths import resolve_spawn_log_dir


def resolve_child_execution_cwd(
    repo_root: Path,
    spawn_id: str,
    harness_id: str,
) -> Path:
    """Determine the actual CWD for a child spawn process.

    When running Claude Code inside Claude Code (CLAUDECODE env set), the child
    process runs from the spawn log directory to avoid task output file collisions.
    See runner.py execute_with_finalization() for the authoritative site.

    This helper mirrors the runner.py condition so execute.py can pre-compute the
    value before session_scope entry. Both sites MUST stay in sync.
    """
    if os.environ.get("CLAUDECODE") and harness_id == HarnessId.CLAUDE.value:
        return resolve_spawn_log_dir(repo_root, spawn_id)
    return repo_root
