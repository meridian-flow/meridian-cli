"""Workspace topology file parsing and evaluated snapshot state."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.config.project_paths import resolve_project_paths

WorkspaceStatus = Literal["none", "present", "invalid"]
WorkspaceFindingCode = Literal[
    "workspace_invalid",
    "workspace_unknown_key",
    "workspace_missing_root",
]

_CONTEXT_ROOTS_KEY = "context-roots"
_CONTEXT_ROOT_PATH_KEY = "path"
_CONTEXT_ROOT_ENABLED_KEY = "enabled"


class WorkspaceFinding(BaseModel):
    """Structured workspace finding surfaced by config/doctor output."""

    model_config = ConfigDict(frozen=True)

    code: WorkspaceFindingCode
    message: str
    payload: dict[str, object] | None = None


class ContextRoot(BaseModel):
    """One parsed `[[context-roots]]` entry."""

    model_config = ConfigDict(frozen=True)

    path: str
    enabled: bool = True
    extra_keys: dict[str, object] = Field(default_factory=dict)


class WorkspaceConfig(BaseModel):
    """Parsed `workspace.local.toml` document (no filesystem evaluation)."""

    model_config = ConfigDict(frozen=True)

    path: Path
    context_roots: tuple[ContextRoot, ...]
    unknown_top_level_keys: tuple[str, ...] = ()


class ResolvedContextRoot(BaseModel):
    """Evaluated context-root entry with resolved filesystem state."""

    model_config = ConfigDict(frozen=True)

    declared_path: str
    resolved_path: Path
    enabled: bool
    exists: bool


class WorkspaceSnapshot(BaseModel):
    """Shared workspace read model consumed by config/doctor/launch code."""

    model_config = ConfigDict(frozen=True)

    status: WorkspaceStatus
    path: Path | None = None
    roots: tuple[ResolvedContextRoot, ...] = ()
    unknown_keys: tuple[str, ...] = ()
    findings: tuple[WorkspaceFinding, ...] = ()

    @property
    def roots_count(self) -> int:
        return len(self.roots)

    @property
    def enabled_roots_count(self) -> int:
        return sum(1 for root in self.roots if root.enabled)

    @property
    def missing_roots_count(self) -> int:
        return sum(1 for root in self.roots if root.enabled and not root.exists)

    @classmethod
    def none(cls) -> WorkspaceSnapshot:
        return cls(status="none")

    @classmethod
    def invalid(cls, *, path: Path, message: str) -> WorkspaceSnapshot:
        normalized = message.strip() or "Workspace file is invalid."
        return cls(
            status="invalid",
            path=path,
            findings=(
                WorkspaceFinding(
                    code="workspace_invalid",
                    message=normalized,
                    payload={"path": path.as_posix()},
                ),
            ),
        )


def get_projectable_roots(snapshot: WorkspaceSnapshot) -> tuple[Path, ...]:
    """Return ordered enabled existing roots for projection."""

    return tuple(
        root.resolved_path
        for root in snapshot.roots
        if root.enabled and root.exists
    )


def _parse_context_root(
    *,
    raw_entry: object,
    entry_index: int,
) -> ContextRoot:
    if not isinstance(raw_entry, dict):
        raise ValueError(
            f"Invalid workspace schema: '{_CONTEXT_ROOTS_KEY}[{entry_index}]' must be a table."
        )
    entry = cast("dict[str, object]", raw_entry)

    if _CONTEXT_ROOT_PATH_KEY not in entry:
        raise ValueError(
            f"Invalid workspace schema: '{_CONTEXT_ROOTS_KEY}[{entry_index}].path' is required."
        )
    raw_path = entry[_CONTEXT_ROOT_PATH_KEY]
    if not isinstance(raw_path, str):
        raise ValueError(
            "Invalid workspace schema: "
            f"'{_CONTEXT_ROOTS_KEY}[{entry_index}].path' must be a string."
        )
    normalized_path = raw_path.strip()
    if not normalized_path:
        raise ValueError(
            "Invalid workspace schema: "
            f"'{_CONTEXT_ROOTS_KEY}[{entry_index}].path' must be non-empty."
        )

    raw_enabled = entry.get(_CONTEXT_ROOT_ENABLED_KEY, True)
    if not isinstance(raw_enabled, bool):
        raise ValueError(
            f"Invalid workspace schema: '{_CONTEXT_ROOTS_KEY}[{entry_index}].enabled' "
            "must be a boolean."
        )

    extra_keys = {
        key: value
        for key, value in entry.items()
        if key not in {_CONTEXT_ROOT_PATH_KEY, _CONTEXT_ROOT_ENABLED_KEY}
    }
    return ContextRoot(
        path=normalized_path,
        enabled=raw_enabled,
        extra_keys=extra_keys,
    )


def parse_workspace_config(path: Path) -> WorkspaceConfig:
    """Parse one `workspace.local.toml` file into a structured document model."""

    try:
        payload_obj = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid workspace TOML: {exc}") from exc

    payload = cast("dict[str, object]", payload_obj)

    raw_context_roots = payload.get(_CONTEXT_ROOTS_KEY, [])
    if not isinstance(raw_context_roots, list):
        raise ValueError(
            f"Invalid workspace schema: '{_CONTEXT_ROOTS_KEY}' must be an array of tables."
        )

    context_roots: list[ContextRoot] = []
    for index, raw_entry in enumerate(cast("list[object]", raw_context_roots), start=1):
        context_roots.append(_parse_context_root(raw_entry=raw_entry, entry_index=index))

    unknown_top_level_keys = tuple(sorted(key for key in payload if key != _CONTEXT_ROOTS_KEY))
    return WorkspaceConfig(
        path=path.resolve(),
        context_roots=tuple(context_roots),
        unknown_top_level_keys=unknown_top_level_keys,
    )


def _resolve_workspace_root_path(*, workspace_file: Path, declared_path: str) -> Path:
    candidate = Path(declared_path).expanduser()
    if not candidate.is_absolute():
        candidate = workspace_file.parent / candidate
    return candidate.resolve()


def _unknown_key_identifiers(config: WorkspaceConfig) -> tuple[str, ...]:
    keys: list[str] = list(config.unknown_top_level_keys)
    for index, root in enumerate(config.context_roots, start=1):
        keys.extend(
            f"{_CONTEXT_ROOTS_KEY}[{index}].{key}"
            for key in sorted(root.extra_keys.keys())
        )
    return tuple(keys)


def _evaluate_workspace_config(config: WorkspaceConfig) -> WorkspaceSnapshot:
    resolved_roots: list[ResolvedContextRoot] = []
    for root in config.context_roots:
        resolved_path = _resolve_workspace_root_path(
            workspace_file=config.path,
            declared_path=root.path,
        )
        resolved_roots.append(
            ResolvedContextRoot(
                declared_path=root.path,
                resolved_path=resolved_path,
                enabled=root.enabled,
                exists=resolved_path.is_dir(),
            )
        )
    roots = tuple(resolved_roots)
    unknown_keys = _unknown_key_identifiers(config)

    findings: list[WorkspaceFinding] = []
    if unknown_keys:
        findings.append(
            WorkspaceFinding(
                code="workspace_unknown_key",
                message=(
                    "Workspace file contains unknown keys: "
                    + ", ".join(unknown_keys)
                    + "."
                ),
                payload={"keys": list(unknown_keys)},
            )
        )

    missing_roots = [
        root.resolved_path.as_posix()
        for root in roots
        if root.enabled and not root.exists
    ]
    if missing_roots:
        findings.append(
            WorkspaceFinding(
                code="workspace_missing_root",
                message="Enabled workspace roots are missing: " + ", ".join(missing_roots),
                payload={"roots": missing_roots},
            )
        )

    return WorkspaceSnapshot(
        status="present",
        path=config.path,
        roots=roots,
        unknown_keys=unknown_keys,
        findings=tuple(findings),
    )


def resolve_workspace_snapshot(repo_root: Path) -> WorkspaceSnapshot:
    """Resolve canonical workspace snapshot from project-root paths."""

    workspace_path = resolve_project_paths(repo_root).workspace_local_toml
    if not workspace_path.exists():
        return WorkspaceSnapshot.none()
    if not workspace_path.is_file():
        return WorkspaceSnapshot.invalid(
            path=workspace_path.resolve(),
            message=f"Workspace path '{workspace_path.as_posix()}' exists but is not a file.",
        )
    try:
        config = parse_workspace_config(workspace_path)
    except ValueError as exc:
        return WorkspaceSnapshot.invalid(path=workspace_path.resolve(), message=str(exc))
    return _evaluate_workspace_config(config)


__all__ = [
    "ContextRoot",
    "ResolvedContextRoot",
    "WorkspaceConfig",
    "WorkspaceFinding",
    "WorkspaceSnapshot",
    "WorkspaceStatus",
    "get_projectable_roots",
    "parse_workspace_config",
    "resolve_workspace_snapshot",
]
