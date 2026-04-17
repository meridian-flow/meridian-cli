"""Project-root Meridian path helpers."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.state.paths import resolve_state_paths

PROJECT_ROOT_IGNORE_TARGETS: tuple[str, ...] = ("workspace.local.toml",)


class ProjectPaths(BaseModel):
    """Resolved project-level paths and project-root Meridian file policy."""

    model_config = ConfigDict(frozen=True)

    repo_root: Path
    execution_cwd: Path

    @property
    def meridian_toml(self) -> Path:
        """Return canonical project config path `<project-root>/meridian.toml`."""

        return self.repo_root / "meridian.toml"

    @property
    def workspace_local_toml(self) -> Path:
        """Return local workspace topology path `<state-root-parent>/workspace.local.toml`."""

        return resolve_state_paths(self.repo_root).root_dir.parent / "workspace.local.toml"

    @property
    def workspace_ignore_targets(self) -> tuple[str, ...]:
        """Return project-root local ignore targets owned by Meridian."""

        return PROJECT_ROOT_IGNORE_TARGETS


def resolve_project_paths(repo_root: Path, execution_cwd: Path | None = None) -> ProjectPaths:
    """Build project paths from repository root and optional execution cwd."""

    resolved_repo_root = repo_root.resolve()
    resolved_execution_cwd = (execution_cwd or repo_root).resolve()
    return ProjectPaths(
        repo_root=resolved_repo_root,
        execution_cwd=resolved_execution_cwd,
    )
