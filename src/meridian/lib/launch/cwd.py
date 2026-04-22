"""Shared CWD resolution for child spawn processes."""

from pathlib import Path


def resolve_child_execution_cwd(
    project_root: Path,
    spawn_id: str,
    harness_id: str,
) -> Path:
    """Determine the actual CWD for a child spawn process.

    Always returns project_root. The former CLAUDECODE-based redirect to the
    spawn log directory has been removed; nested Claude delegation boundaries
    are enforced via disallowed tool resolution in launch/permissions.py.
    """
    _ = spawn_id, harness_id
    return project_root
