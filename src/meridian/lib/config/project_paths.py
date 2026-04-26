"""Project-root Meridian path helpers."""

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

PROJECT_ROOT_IGNORE_TARGETS: tuple[str, ...] = (
    "workspace.local.toml",
    "meridian.local.toml",
)


class ProjectConfigPaths(BaseModel):
    """Resolved project-level paths and project-root Meridian file policy."""

    model_config = ConfigDict(frozen=True)

    project_root: Path
    execution_cwd: Path

    @property
    def meridian_toml(self) -> Path:
        """Return canonical project config path `<project-root>/meridian.toml`."""

        return self.project_root / "meridian.toml"

    @property
    def workspace_local_toml(self) -> Path:
        """Return local workspace topology path `<state-root-parent>/workspace.local.toml`."""

        override = os.getenv("MERIDIAN_RUNTIME_DIR", "").strip()
        if not override:
            return self.project_root / "workspace.local.toml"

        candidate = Path(override).expanduser()
        runtime_root = candidate if candidate.is_absolute() else self.project_root / candidate
        return runtime_root.parent / "workspace.local.toml"

    @property
    def meridian_local_toml(self) -> Path:
        """Return local override path `<project-root>/meridian.local.toml`."""

        return self.project_root / "meridian.local.toml"

    @property
    def workspace_ignore_targets(self) -> tuple[str, ...]:
        """Return project-root local ignore targets owned by Meridian."""

        return PROJECT_ROOT_IGNORE_TARGETS


def resolve_project_config_paths(
    project_root: Path, execution_cwd: Path | None = None
) -> ProjectConfigPaths:
    """Build project paths from repository root and optional execution cwd."""

    resolved_project_root = project_root.resolve()
    resolved_execution_cwd = (execution_cwd or project_root).resolve()
    return ProjectConfigPaths(
        project_root=resolved_project_root,
        execution_cwd=resolved_execution_cwd,
    )
