"""Operation runtime helpers for state/store resolution."""


from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.config.settings import resolve_repo_root
from meridian.lib.config.settings import MeridianConfig, load_config
from meridian.lib.core.sink import NullSink, OutputSink
from meridian.lib.state.artifact_store import LocalStore
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.core.types import SpaceId

SPACE_REQUIRED_ERROR = (
    "ERROR [SPACE_REQUIRED]: Spawn commands require explicit space context. "
    "Set MERIDIAN_SPACE_ID or pass --space."
)


class OperationRuntime(BaseModel):
    """Resolved dependencies used by operation handlers."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    repo_root: Path
    config: MeridianConfig
    harness_registry: Any  # HarnessRegistry — typed as Any to avoid circular import
    artifacts: LocalStore
    sink: OutputSink = Field(default_factory=NullSink)


def resolve_runtime_root_and_config(
    repo_root: str | None = None,
    *,
    sink: OutputSink | None = None,
) -> tuple[Path, MeridianConfig]:
    """Resolve repository root and load operational config."""

    _ = sink
    explicit_root = Path(repo_root).expanduser().resolve() if repo_root else None
    resolved_root = resolve_repo_root(explicit_root)
    return resolved_root, load_config(resolved_root)


def build_runtime_from_root_and_config(
    repo_root: Path,
    config: MeridianConfig,
    *,
    sink: OutputSink | None = None,
) -> OperationRuntime:
    """Build a runtime bundle from one pre-resolved root and config."""

    from meridian.lib.harness.registry import get_default_harness_registry

    return OperationRuntime(
        repo_root=repo_root,
        config=config,
        harness_registry=get_default_harness_registry(),
        artifacts=LocalStore(root_dir=resolve_state_paths(repo_root).artifacts_dir),
        sink=sink or NullSink(),
    )


def build_runtime(
    repo_root: str | None = None,
    *,
    sink: OutputSink | None = None,
) -> OperationRuntime:
    """Build a runtime bundle rooted at one repository path."""

    resolved_root, config = resolve_runtime_root_and_config(repo_root, sink=sink)
    return build_runtime_from_root_and_config(resolved_root, config, sink=sink)


def _normalize_space_id(space_id: str | SpaceId | None) -> str:
    if space_id is None:
        return ""
    return str(space_id).strip()


def require_space_id(
    space: str | None,
    *,
    space_id: str | SpaceId | None = None,
) -> SpaceId:
    """Resolve space ID and raise when none is configured."""

    resolved = space.strip() if space is not None else ""
    if not resolved:
        resolved = _normalize_space_id(space_id)
    if not resolved:
        raise ValueError(SPACE_REQUIRED_ERROR)
    return SpaceId(resolved)


def resolve_space_id_or_none(
    space: str | None,
    *,
    space_id: str | SpaceId | None = None,
) -> str | None:
    """Resolve space ID from explicit value or fallback, returning None if absent."""

    resolved = space.strip() if space is not None else ""
    if not resolved:
        resolved = _normalize_space_id(space_id)
    return resolved or None
