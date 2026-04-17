"""Workspace-root projection contract shared by harness adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.harness.ids import HarnessId

WorkspaceApplicability = Literal[
    "active",
    "unsupported:requires_config_generation",
    "ignored:no_roots",
]
WorkspaceProjectionDiagnosticCode = Literal["workspace_opencode_parent_env_suppressed"]

OPENCODE_CONFIG_CONTENT_ENV = "OPENCODE_CONFIG_CONTENT"


class WorkspaceProjectionDiagnostic(BaseModel):
    """One user-visible diagnostic emitted by workspace projection."""

    model_config = ConfigDict(frozen=True)

    code: WorkspaceProjectionDiagnosticCode
    message: str
    payload: dict[str, object] | None = None


class ProjectionResult(BaseModel):
    """Projection result consumed by launch composition and inspection surfaces."""

    model_config = ConfigDict(frozen=True)

    applicability: WorkspaceApplicability
    args: tuple[str, ...] = ()
    env_overrides: dict[str, str] = Field(default_factory=dict)
    diagnostics: tuple[WorkspaceProjectionDiagnostic, ...] = ()


def _project_claude_workspace_args(roots: tuple[Path, ...]) -> tuple[str, ...]:
    projected: list[str] = []
    for root in roots:
        projected.extend(("--add-dir", root.as_posix()))
    return tuple(projected)


def _build_opencode_workspace_config(roots: tuple[Path, ...]) -> str:
    return json.dumps(
        {
            "permission": {
                "external_directory": [root.as_posix() for root in roots],
            }
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def project_workspace_roots(
    *,
    harness_id: HarnessId,
    roots: tuple[Path, ...],
    parent_opencode_config_content: str | None = None,
) -> ProjectionResult:
    """Project workspace roots for one harness launch/inspection pass."""

    if not roots:
        return ProjectionResult(applicability="ignored:no_roots")

    if harness_id == HarnessId.CLAUDE:
        return ProjectionResult(
            applicability="active",
            args=_project_claude_workspace_args(roots),
        )

    if harness_id == HarnessId.OPENCODE:
        parent_config = (parent_opencode_config_content or "").strip()
        if parent_config:
            return ProjectionResult(
                applicability="active",
                diagnostics=(
                    WorkspaceProjectionDiagnostic(
                        code="workspace_opencode_parent_env_suppressed",
                        message=(
                            "Workspace projection for OpenCode was suppressed because "
                            "parent OPENCODE_CONFIG_CONTENT is already set."
                        ),
                        payload={"env_var": OPENCODE_CONFIG_CONTENT_ENV},
                    ),
                ),
            )
        return ProjectionResult(
            applicability="active",
            env_overrides={
                OPENCODE_CONFIG_CONTENT_ENV: _build_opencode_workspace_config(roots)
            },
        )

    return ProjectionResult(applicability="unsupported:requires_config_generation")


__all__ = [
    "OPENCODE_CONFIG_CONTENT_ENV",
    "ProjectionResult",
    "WorkspaceApplicability",
    "WorkspaceProjectionDiagnostic",
    "WorkspaceProjectionDiagnosticCode",
    "project_workspace_roots",
]
