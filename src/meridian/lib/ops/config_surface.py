"""Shared config/workspace inspection surface for config and doctor ops."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.config.project_config_state import (
    ProjectConfigState,
    resolve_project_config_state,
)
from meridian.lib.config.settings import MeridianConfig, load_config, resolve_user_config_path


class ConfigSurface(BaseModel):
    """Observed config surface shared by inspection commands."""

    model_config = ConfigDict(frozen=True)

    repo_root: Path
    project_config: ProjectConfigState
    user_config_path: Path | None
    resolved_config: MeridianConfig
    warning: str | None = None


def build_config_surface(repo_root: Path) -> ConfigSurface:
    """Build shared config inspection state for one resolved repository root."""

    resolved_root = repo_root.expanduser().resolve()
    user_config_path = resolve_user_config_path(None)
    warning: str | None = None
    if not resolved_root.exists():
        warning = f"Resolved project root '{resolved_root.as_posix()}' does not exist on disk."

    return ConfigSurface(
        repo_root=resolved_root,
        project_config=resolve_project_config_state(resolved_root),
        user_config_path=user_config_path,
        resolved_config=load_config(
            resolved_root,
            user_config=user_config_path,
            resolve_models=False,
        ),
        warning=warning,
    )
