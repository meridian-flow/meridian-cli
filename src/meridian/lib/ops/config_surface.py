"""Shared config/workspace inspection surface for config and doctor ops."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.config.project_config_state import (
    ProjectConfigState,
    resolve_project_config_state,
)
from meridian.lib.config.project_root import resolve_user_config_path
from meridian.lib.config.settings import MeridianConfig, load_config
from meridian.lib.config.workspace import (
    WorkspaceFinding,
    WorkspaceSnapshot,
    WorkspaceStatus,
    get_projectable_roots,
    resolve_workspace_snapshot,
)
from meridian.lib.harness.ids import HarnessId
from meridian.lib.harness.workspace_projection import (
    WorkspaceApplicability,
    project_workspace_roots,
)


class ConfigSurfaceWorkspaceRoots(BaseModel):
    """Workspace root counts surfaced by inspection commands."""

    model_config = ConfigDict(frozen=True)

    count: int
    enabled: int
    missing: int


class ConfigSurfaceWorkspace(BaseModel):
    """Minimal workspace summary payload used by `config show`."""

    model_config = ConfigDict(frozen=True)

    status: WorkspaceStatus
    path: str | None = None
    roots: ConfigSurfaceWorkspaceRoots
    applicability: dict[str, WorkspaceApplicability]

    @classmethod
    def from_snapshot(cls, snapshot: WorkspaceSnapshot) -> ConfigSurfaceWorkspace:
        projectable_roots = get_projectable_roots(snapshot)
        return cls(
            status=snapshot.status,
            path=snapshot.path.as_posix() if snapshot.path is not None else None,
            roots=ConfigSurfaceWorkspaceRoots(
                count=snapshot.roots_count,
                enabled=snapshot.enabled_roots_count,
                missing=snapshot.missing_roots_count,
            ),
            applicability={
                HarnessId.CLAUDE.value: project_workspace_roots(
                    harness_id=HarnessId.CLAUDE,
                    roots=projectable_roots,
                ).applicability,
                HarnessId.CODEX.value: project_workspace_roots(
                    harness_id=HarnessId.CODEX,
                    roots=projectable_roots,
                ).applicability,
                HarnessId.OPENCODE.value: project_workspace_roots(
                    harness_id=HarnessId.OPENCODE,
                    roots=projectable_roots,
                ).applicability,
            },
        )


class ConfigSurface(BaseModel):
    """Observed config surface shared by inspection commands."""

    model_config = ConfigDict(frozen=True)

    project_root: Path
    project_config: ProjectConfigState
    user_config_path: Path | None
    resolved_config: MeridianConfig
    workspace: ConfigSurfaceWorkspace
    workspace_findings: tuple[WorkspaceFinding, ...] = ()
    warning: str | None = None


def build_config_surface(project_root: Path) -> ConfigSurface:
    """Build shared config inspection state for one resolved repository root."""

    resolved_root = project_root.expanduser().resolve()
    user_config_path = resolve_user_config_path(None)
    warning: str | None = None
    if not resolved_root.exists():
        warning = f"Resolved project root '{resolved_root.as_posix()}' does not exist on disk."
    workspace_snapshot = resolve_workspace_snapshot(resolved_root)

    return ConfigSurface(
        project_root=resolved_root,
        project_config=resolve_project_config_state(resolved_root),
        user_config_path=user_config_path,
        resolved_config=load_config(
            resolved_root,
            user_config=user_config_path,
            resolve_models=False,
        ),
        workspace=ConfigSurfaceWorkspace.from_snapshot(workspace_snapshot),
        workspace_findings=workspace_snapshot.findings,
        warning=warning,
    )
