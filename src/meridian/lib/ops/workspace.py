"""Workspace file operations."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.config.project_paths import resolve_project_paths
from meridian.lib.config.settings import resolve_project_root
from meridian.lib.core.util import FormatContext
from meridian.lib.ops.runtime import async_from_sync
from meridian.lib.state.atomic import atomic_write_text

_WORKSPACE_TEMPLATE = """# Workspace topology — local-only, gitignored.
# Uncomment and fill paths to enable workspace roots.
#
# [[context-roots]]
# path = "../sibling-repo"
# enabled = true
"""


class WorkspaceInitInput(BaseModel):
    """Input model for `workspace init`."""

    model_config = ConfigDict(frozen=True)

    repo_root: str | None = None


class WorkspaceInitOutput(BaseModel):
    """Result payload for `workspace init`."""

    model_config = ConfigDict(frozen=True)

    path: str
    created: bool
    local_gitignore_path: str | None = None
    local_gitignore_updated: bool = False

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        status = "created" if self.created else "exists"
        lines = [f"{status}: {self.path}"]
        if self.local_gitignore_path is None:
            lines.append("local_gitignore: unavailable")
            return "\n".join(lines)
        coverage = "updated" if self.local_gitignore_updated else "ok"
        lines.append(f"local_gitignore: {self.local_gitignore_path} ({coverage})")
        return "\n".join(lines)


def _resolve_git_dir(repo_root: Path) -> Path | None:
    git_entry = repo_root / ".git"
    if git_entry.is_dir():
        return git_entry.resolve()
    if not git_entry.is_file():
        return None

    for line in git_entry.read_text(encoding="utf-8").splitlines():
        normalized = line.strip()
        if not normalized:
            continue
        prefix = "gitdir:"
        if not normalized.lower().startswith(prefix):
            break
        raw_target = normalized[len(prefix) :].strip()
        if not raw_target:
            break
        target = Path(raw_target).expanduser()
        if not target.is_absolute():
            target = (repo_root / target).resolve()
        if target.is_dir():
            return target
        break
    return None


def _ensure_local_gitignore_entries(
    *,
    repo_root: Path,
    entries: tuple[str, ...],
) -> tuple[Path | None, bool]:
    git_dir = _resolve_git_dir(repo_root)
    if git_dir is None:
        return None, False

    exclude_path = git_dir / "info" / "exclude"
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    existing_text = (
        exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
    )
    existing_lines = existing_text.splitlines()
    present = {line.strip() for line in existing_lines}
    missing_entries = [entry for entry in entries if entry not in present]
    if not missing_entries:
        return exclude_path, False

    updated_lines = list(existing_lines)
    if updated_lines and updated_lines[-1].strip():
        updated_lines.append("")
    updated_lines.append("# Added by Meridian local workspace init")
    updated_lines.extend(missing_entries)
    updated_text = "\n".join(updated_lines).rstrip() + "\n"
    atomic_write_text(exclude_path, updated_text)
    return exclude_path, True


def workspace_init_sync(payload: WorkspaceInitInput) -> WorkspaceInitOutput:
    explicit_root = Path(payload.repo_root).expanduser().resolve() if payload.repo_root else None
    repo_root = resolve_project_root(explicit_root)
    project_paths = resolve_project_paths(repo_root=repo_root)

    workspace_path = project_paths.workspace_local_toml
    created = False
    if not workspace_path.exists():
        atomic_write_text(workspace_path, _WORKSPACE_TEMPLATE)
        created = True
    elif not workspace_path.is_file():
        raise ValueError(
            f"Workspace path '{workspace_path.as_posix()}' exists but is not a file."
        )

    local_gitignore_path, local_gitignore_updated = _ensure_local_gitignore_entries(
        repo_root=repo_root,
        entries=project_paths.workspace_ignore_targets,
    )

    return WorkspaceInitOutput(
        path=workspace_path.as_posix(),
        created=created,
        local_gitignore_path=(
            local_gitignore_path.as_posix() if local_gitignore_path is not None else None
        ),
        local_gitignore_updated=local_gitignore_updated,
    )


workspace_init = async_from_sync(workspace_init_sync)


__all__ = [
    "WorkspaceInitInput",
    "WorkspaceInitOutput",
    "workspace_init",
    "workspace_init_sync",
]
