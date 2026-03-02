"""Operation registry shared by CLI, MCP, and DirectAdapter surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


@dataclass(frozen=True, slots=True)
class OperationSpec(Generic[InputT, OutputT]):
    """Single source of truth for an operation exposed on both surfaces."""

    name: str
    handler: Callable[[InputT], Coroutine[Any, Any, OutputT]]
    input_type: type[InputT]
    output_type: type[OutputT]
    cli_group: str | None
    cli_name: str
    mcp_name: str
    description: str
    version: str = "1"
    sync_handler: Callable[[InputT], OutputT] | None = None
    cli_only: bool = False
    mcp_only: bool = False


_REGISTRY: dict[str, OperationSpec[Any, Any]] = {}
_bootstrapped = False


def operation(spec: OperationSpec[InputT, OutputT]) -> OperationSpec[InputT, OutputT]:
    """Register an operation and guard against duplicates."""

    if spec.cli_only and spec.mcp_only:
        raise ValueError(f"Operation '{spec.name}' cannot be both cli_only and mcp_only")
    if spec.name in _REGISTRY:
        raise ValueError(
            f"Duplicate operation name '{spec.name}': already registered by "
            f"{_REGISTRY[spec.name].handler}"
        )
    _REGISTRY[spec.name] = spec
    return spec


def get_all_operations() -> list[OperationSpec[Any, Any]]:
    """Return all registered operations sorted by canonical name."""

    _ensure_bootstrapped()
    return [_REGISTRY[name] for name in sorted(_REGISTRY)]


def get_operation(name: str) -> OperationSpec[Any, Any]:
    """Fetch one operation spec by canonical name."""

    _ensure_bootstrapped()
    return _REGISTRY[name]


def get_mcp_tool_names() -> frozenset[str]:
    """Return non-CLI MCP tool names from the operation registry."""

    _ensure_bootstrapped()
    return frozenset(spec.mcp_name for spec in _REGISTRY.values() if not spec.cli_only)


def _bootstrap_operation_modules() -> None:
    # Imported lazily to keep the registry as the single source of truth while
    # allowing operation modules to self-register via `operation(...)`.
    import meridian.lib.ops.config as config_ops
    import meridian.lib.ops.diag as diag_ops
    import meridian.lib.ops.models as models_ops
    import meridian.lib.ops.spawn as spawn_ops
    import meridian.lib.ops.skills as skills_ops
    import meridian.lib.ops.space as space_ops

    _ = (
        config_ops,
        diag_ops,
        models_ops,
        spawn_ops,
        skills_ops,
        space_ops,
    )


def _ensure_bootstrapped() -> None:
    global _bootstrapped
    if _bootstrapped:
        return
    # Only mark bootstrapped after a successful import sequence so failures retry.
    _bootstrap_operation_modules()
    _bootstrapped = True
