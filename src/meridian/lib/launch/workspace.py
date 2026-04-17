"""Launch-time workspace policy gates."""

from pathlib import Path

from meridian.lib.config.workspace import WorkspaceSnapshot, resolve_workspace_snapshot


def resolve_workspace_snapshot_for_launch(repo_root: Path) -> WorkspaceSnapshot:
    """Resolve launch workspace snapshot and raise on invalid topology."""

    snapshot = resolve_workspace_snapshot(repo_root)
    if snapshot.status != "invalid":
        return snapshot
    details = "; ".join(finding.message for finding in snapshot.findings if finding.message.strip())
    if not details:
        details = "Workspace file is invalid."
    path = snapshot.path.as_posix() if snapshot.path is not None else "workspace.local.toml"
    raise ValueError(
        f"Invalid workspace file '{path}'. {details} "
        "Run `meridian config show` or `meridian doctor` for details."
    )


def ensure_workspace_valid_for_launch(repo_root: Path) -> None:
    """Raise when workspace topology is invalid for launch-time commands."""

    resolve_workspace_snapshot_for_launch(repo_root)


__all__ = ["ensure_workspace_valid_for_launch", "resolve_workspace_snapshot_for_launch"]
