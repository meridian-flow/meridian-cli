"""Permission configuration and resolver construction."""

from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


type SandboxMode = Literal[
    "default",
    "read-only",
    "workspace-write",
    "danger-full-access",
]


type ApprovalMode = Literal[
    "default",
    "auto",
    "yolo",
    "confirm",
]


_SANDBOX_MODES: frozenset[SandboxMode] = frozenset(
    {
        "default",
        "read-only",
        "workspace-write",
        "danger-full-access",
    }
)

_APPROVAL_MODES: frozenset[ApprovalMode] = frozenset(
    {
        "default",
        "auto",
        "yolo",
        "confirm",
    }
)


class PermissionConfig(BaseModel):
    """Transport-neutral permission intent."""

    model_config = ConfigDict(frozen=True)

    sandbox: SandboxMode = "default"
    approval: ApprovalMode = "default"
    # Optional OpenCode permission map JSON derived from explicit tool lists.
    opencode_permission_override: str | None = None


def _install_readonly_permission_field(field_name: str) -> None:
    def _get(instance: PermissionConfig) -> object:
        return instance.__dict__[field_name]

    def _set(instance: PermissionConfig, value: object) -> None:
        _ = instance, value
        raise TypeError(f"PermissionConfig is frozen; cannot mutate '{field_name}'.")

    setattr(PermissionConfig, field_name, property(_get, _set))


for _field_name in ("sandbox", "approval", "opencode_permission_override"):
    _install_readonly_permission_field(_field_name)


class UnsafeNoOpPermissionResolver(BaseModel):
    """Explicit unsafe opt-out resolver with no permission enforcement."""

    model_config = ConfigDict(frozen=True)

    def __init__(self, *, _suppress_warning: bool = False, **data: object) -> None:
        super().__init__(**data)
        if not _suppress_warning:
            logger.warning(
                "UnsafeNoOpPermissionResolver constructed; "
                "no permission enforcement will be applied"
            )

    @property
    def config(self) -> PermissionConfig:
        return PermissionConfig()

    def resolve_flags(self) -> tuple[str, ...]:
        return ()


def _parse_approval_value(raw: str) -> ApprovalMode:
    normalized = raw.strip().lower()
    if normalized in _APPROVAL_MODES:
        return normalized
    allowed = ", ".join(sorted(_APPROVAL_MODES))
    raise ValueError(f"Unsupported approval mode '{raw}'. Expected: {allowed}.")


def _parse_sandbox_value(raw: str | None) -> SandboxMode:
    normalized = raw.strip().lower() if raw else "default"
    if normalized in _SANDBOX_MODES:
        return normalized
    allowed = ", ".join(sorted(_SANDBOX_MODES))
    raise ValueError(f"Unsupported sandbox mode '{raw}'. Expected: {allowed}.")


def build_permission_config(
    sandbox: str | None,
    *,
    approval: str = "default",
) -> PermissionConfig:
    """Build and validate a permission configuration."""

    return PermissionConfig(
        sandbox=_parse_sandbox_value(sandbox),
        approval=_parse_approval_value(approval),
    )


def _normalize_tool_name(raw: str) -> str:
    """Normalize a tool name: strip Claude-style qualifiers and lowercase."""
    return raw.split("(", 1)[0].strip().lower()


def opencode_permission_json_for_allowed_tools(allowed_tools: tuple[str, ...]) -> str:
    """Build OpenCode permission JSON from an explicit allowed-tools tuple."""

    permissions: dict[str, str] = {"*": "deny"}
    for raw_tool in allowed_tools:
        normalized = _normalize_tool_name(raw_tool)
        if not normalized:
            continue
        permissions[normalized] = "allow"
    return json.dumps(permissions, sort_keys=True, separators=(",", ":"))


def opencode_permission_json_for_disallowed_tools(disallowed_tools: tuple[str, ...]) -> str:
    """Build OpenCode permission JSON from an explicit disallowed-tools tuple."""

    permissions: dict[str, str] = {"*": "allow"}
    for raw_tool in disallowed_tools:
        normalized = _normalize_tool_name(raw_tool)
        if not normalized:
            continue
        permissions[normalized] = "deny"
    return json.dumps(permissions, sort_keys=True, separators=(",", ":"))


class TieredPermissionResolver(BaseModel):
    """PermissionResolver implementation backed by one permission config."""

    model_config = ConfigDict(frozen=True)

    config: PermissionConfig

    def resolve_flags(self) -> tuple[str, ...]:
        return ()


class ExplicitToolsResolver(BaseModel):
    """PermissionResolver backed by an explicit tool allowlist."""

    model_config = ConfigDict(frozen=True)

    allowed_tools: tuple[str, ...]
    fallback_config: PermissionConfig

    @property
    def config(self) -> PermissionConfig:
        return self.fallback_config

    def opencode_permission_json(self) -> str:
        return opencode_permission_json_for_allowed_tools(self.allowed_tools)

    def resolve_flags(self) -> tuple[str, ...]:
        filtered = tuple(tool for tool in self.allowed_tools if tool.strip())
        if not filtered:
            return ()
        return ("--allowedTools", ",".join(filtered))


class DisallowedToolsResolver(BaseModel):
    """PermissionResolver backed by an explicit tool denylist."""

    model_config = ConfigDict(frozen=True)

    disallowed_tools: tuple[str, ...]
    fallback_config: PermissionConfig

    @property
    def config(self) -> PermissionConfig:
        return self.fallback_config

    def opencode_permission_json(self) -> str:
        return opencode_permission_json_for_disallowed_tools(self.disallowed_tools)

    def resolve_flags(self) -> tuple[str, ...]:
        filtered = tuple(tool for tool in self.disallowed_tools if tool.strip())
        if not filtered:
            return ()
        return ("--disallowedTools", ",".join(filtered))


class CombinedToolsResolver(BaseModel):
    """PermissionResolver that combines allowlist and denylist controls."""

    model_config = ConfigDict(frozen=True)

    allowlist: ExplicitToolsResolver | None = None
    denylist: DisallowedToolsResolver | None = None

    @property
    def config(self) -> PermissionConfig:
        if self.allowlist is not None:
            return self.allowlist.config
        if self.denylist is not None:
            return self.denylist.config
        return PermissionConfig()

    def resolve_flags(self) -> tuple[str, ...]:
        flags: list[str] = []
        if self.allowlist is not None:
            flags.extend(self.allowlist.resolve_flags())
        if self.denylist is not None:
            flags.extend(self.denylist.resolve_flags())
        return tuple(flags)

    def opencode_permission_json(self) -> str | None:
        if self.allowlist is not None:
            return self.allowlist.opencode_permission_json()
        if self.denylist is not None:
            return self.denylist.opencode_permission_json()
        return None


def _resolve_opencode_override(
    *,
    allowed_tools: tuple[str, ...],
    disallowed_tools: tuple[str, ...],
) -> str | None:
    if allowed_tools:
        return opencode_permission_json_for_allowed_tools(allowed_tools)
    if disallowed_tools:
        return opencode_permission_json_for_disallowed_tools(disallowed_tools)
    return None


def build_permission_resolver(
    *,
    allowed_tools: tuple[str, ...],
    disallowed_tools: tuple[str, ...],
    permission_config: PermissionConfig,
) -> (
    TieredPermissionResolver
    | ExplicitToolsResolver
    | DisallowedToolsResolver
    | CombinedToolsResolver
):
    """Pick the right resolver: explicit tools if specified, else config-based."""
    if disallowed_tools:
        return CombinedToolsResolver(
            allowlist=(
                ExplicitToolsResolver(
                    allowed_tools=allowed_tools,
                    fallback_config=permission_config,
                )
                if allowed_tools
                else None
            ),
            denylist=(
                DisallowedToolsResolver(
                    disallowed_tools=disallowed_tools,
                    fallback_config=permission_config,
                )
                if disallowed_tools
                else None
            ),
        )
    if allowed_tools:
        return ExplicitToolsResolver(
            allowed_tools=allowed_tools,
            fallback_config=permission_config,
        )
    return TieredPermissionResolver(config=permission_config)


def resolve_permission_pipeline(
    *,
    sandbox: str | None,
    allowed_tools: tuple[str, ...] = (),
    disallowed_tools: tuple[str, ...] = (),
    approval: str = "default",
) -> tuple[
    PermissionConfig,
    (
        TieredPermissionResolver
        | ExplicitToolsResolver
        | DisallowedToolsResolver
        | CombinedToolsResolver
    ),
]:
    config = build_permission_config(sandbox, approval=approval)
    opencode_override = _resolve_opencode_override(
        allowed_tools=allowed_tools,
        disallowed_tools=disallowed_tools,
    )
    if opencode_override is not None:
        config = config.model_copy(update={"opencode_permission_override": opencode_override})

    resolver = build_permission_resolver(
        allowed_tools=allowed_tools,
        disallowed_tools=disallowed_tools,
        permission_config=config,
    )
    return config, resolver
