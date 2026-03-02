"""Operation runtime helpers for state/store resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from meridian.lib.config._paths import resolve_repo_root
from meridian.lib.config.settings import MeridianConfig, load_config
from meridian.lib.harness.registry import HarnessRegistry, get_default_harness_registry
from meridian.lib.state.artifact_store import LocalStore
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.types import SpaceId

SPACE_REQUIRED_ERROR = (
    "ERROR [SPACE_REQUIRED]: Spawn commands require explicit space context. "
    "Set MERIDIAN_SPACE_ID or pass --space."
)


@dataclass(frozen=True, slots=True)
class OperationRuntime:
    """Resolved dependencies used by operation handlers."""

    repo_root: Path
    config: MeridianConfig
    harness_registry: HarnessRegistry
    artifacts: LocalStore


def resolve_runtime_root_and_config(
    repo_root: str | None = None,
) -> tuple[Path, MeridianConfig]:
    """Resolve repository root and load operational config."""

    explicit_root = Path(repo_root).expanduser().resolve() if repo_root else None
    resolved_root = resolve_repo_root(explicit_root)
    return resolved_root, load_config(resolved_root)


def build_runtime_from_root_and_config(
    repo_root: Path,
    config: MeridianConfig,
) -> OperationRuntime:
    """Build a runtime bundle from one pre-resolved root and config."""

    return OperationRuntime(
        repo_root=repo_root,
        config=config,
        harness_registry=get_default_harness_registry(),
        artifacts=LocalStore(resolve_state_paths(repo_root).artifacts_dir),
    )


def build_runtime(repo_root: str | None = None) -> OperationRuntime:
    """Build a runtime bundle rooted at one repository path."""

    resolved_root, config = resolve_runtime_root_and_config(repo_root)
    return build_runtime_from_root_and_config(resolved_root, config)


def resolve_space_id(space: str | None) -> SpaceId | None:
    """Resolve space from explicit input or environment."""

    resolved = space.strip() if space is not None else ""
    if not resolved:
        resolved = os.getenv("MERIDIAN_SPACE_ID", "").strip()
    if not resolved:
        return None
    return SpaceId(resolved)


def require_space_id(space: str | None) -> SpaceId:
    """Resolve space ID and raise when none is configured."""

    resolved = resolve_space_id(space)
    if resolved is None:
        raise ValueError(SPACE_REQUIRED_ERROR)
    return resolved
