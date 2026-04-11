"""Leaf launch contracts shared across harness adapters and runners."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from meridian.lib.safety.permissions import PermissionConfig


class _NoOpPermissionResolver:
    """Fallback resolver for call sites that do not provide explicit permissions."""

    @property
    def config(self) -> PermissionConfig:
        from meridian.lib.safety.permissions import PermissionConfig

        return PermissionConfig()

    def resolve_flags(self) -> tuple[str, ...]:
        return ()


@runtime_checkable
class PermissionResolver(Protocol):
    """Transport-neutral permission intent resolver."""

    @property
    def config(self) -> PermissionConfig: ...

    def resolve_flags(self) -> tuple[str, ...]:
        return ()


class ResolvedLaunchSpec(BaseModel):
    """Transport-neutral resolved configuration for one harness launch."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    # Identity
    model: str | None = None

    # Execution parameters
    effort: str | None = None
    prompt: str = ""

    # Session continuity
    continue_session_id: str | None = None
    continue_fork: bool = False

    # Permissions
    permission_resolver: PermissionResolver = Field(default_factory=_NoOpPermissionResolver)

    # Passthrough args forwarded verbatim to the harness process.
    extra_args: tuple[str, ...] = ()

    # Interactive mode
    interactive: bool = False

    # Optional output path (currently consumed by codex subprocess transport).
    report_output_path: str | None = None

    # Harness-agnostic MCP tool configuration.
    mcp_tools: tuple[str, ...] = ()

    @property
    def permission_config(self) -> PermissionConfig:
        """Compatibility view for code that still expects resolved permission config."""
        return self.permission_resolver.config

    @model_validator(mode="after")
    def _validate_continue_fork_requires_session(self) -> ResolvedLaunchSpec:
        if self.continue_fork and not self.continue_session_id:
            raise ValueError("continue_fork=True requires continue_session_id")
        return self


SpecT = TypeVar("SpecT", bound=ResolvedLaunchSpec)


@dataclass(frozen=True)
class PreflightResult:
    """Result of adapter-owned preflight."""

    expanded_passthrough_args: tuple[str, ...]
    extra_env: MappingProxyType[str, str]

    @classmethod
    def build(
        cls,
        *,
        expanded_passthrough_args: tuple[str, ...],
        extra_env: dict[str, str] | None = None,
    ) -> PreflightResult:
        return cls(
            expanded_passthrough_args=expanded_passthrough_args,
            extra_env=MappingProxyType(dict(extra_env or {})),
        )
