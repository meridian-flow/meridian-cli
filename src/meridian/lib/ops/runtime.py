"""Operation runtime helpers for state/store resolution."""


from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.config.settings import resolve_repo_root
from meridian.lib.config.settings import MeridianConfig, load_config
from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.sink import NullSink, OutputSink
from meridian.lib.state.artifact_store import LocalStore
from meridian.lib.state.paths import resolve_state_paths


class OperationRuntime(BaseModel):
    """Resolved dependencies used by operation handlers."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    repo_root: Path
    config: MeridianConfig
    harness_registry: Any  # HarnessRegistry — typed as Any to avoid circular import
    artifacts: LocalStore
    sink: OutputSink = Field(default_factory=NullSink)


@dataclass(frozen=True)
class ResolvedRoots:
    repo_root: Path
    state_root: Path


def runtime_context(ctx: RuntimeContext | None) -> RuntimeContext:
    if ctx is not None:
        return ctx
    return RuntimeContext.from_environment()


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


def resolve_state_root(repo_root: Path) -> Path:
    """Resolve the Meridian state root for a repository."""

    return resolve_state_paths(repo_root).root_dir


def resolve_roots(repo_root: str | None) -> ResolvedRoots:
    resolved_repo_root, _ = resolve_runtime_root_and_config(repo_root)
    return ResolvedRoots(
        repo_root=resolved_repo_root,
        state_root=resolve_state_root(resolved_repo_root),
    )


def resolve_chat_id(
    *,
    payload_chat_id: str = "",
    ctx: RuntimeContext | None = None,
    fallback: str = "",
) -> str:
    normalized = payload_chat_id.strip()
    if normalized:
        return normalized
    resolved_chat_id = runtime_context(ctx).chat_id.strip()
    if resolved_chat_id:
        return resolved_chat_id
    return fallback.strip()
