"""Permission-resolution stage ownership for launch composition."""

from __future__ import annotations

from meridian.lib.safety.permissions import (
    CombinedToolsResolver,
    DisallowedToolsResolver,
    ExplicitToolsResolver,
    PermissionConfig,
    TieredPermissionResolver,
    UnsafeNoOpPermissionResolver,
    build_permission_config,
    build_permission_resolver,
    opencode_permission_json_for_allowed_tools,
    opencode_permission_json_for_disallowed_tools,
)

PermissionResolverImpl = (
    TieredPermissionResolver
    | ExplicitToolsResolver
    | DisallowedToolsResolver
    | CombinedToolsResolver
    | UnsafeNoOpPermissionResolver
)


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


def resolve_permission_pipeline(
    *,
    sandbox: str | None,
    allowed_tools: tuple[str, ...] = (),
    disallowed_tools: tuple[str, ...] = (),
    approval: str = "default",
    unsafe_no_permissions: bool = False,
) -> tuple[PermissionConfig, PermissionResolverImpl]:
    """Resolve a permission config and concrete resolver for one launch request."""

    if unsafe_no_permissions:
        return PermissionConfig(), UnsafeNoOpPermissionResolver()

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


__all__ = ["PermissionResolverImpl", "resolve_permission_pipeline"]
