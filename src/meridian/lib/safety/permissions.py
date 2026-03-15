"""Permission tiers and harness-flag translation."""


import logging
import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.types import HarnessId

logger = logging.getLogger(__name__)


class PermissionTier(StrEnum):
    """Safety tiers applied to harness command construction."""

    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    FULL_ACCESS = "full-access"


_APPROVAL_MODES = frozenset({"confirm", "auto"})


class PermissionConfig(BaseModel):
    """Resolved permission configuration for one run."""

    model_config = ConfigDict(frozen=True)

    tier: PermissionTier | None = None
    approval: str = "confirm"
    # Optional OpenCode permission map JSON derived from explicit allowed_tools.
    # When set, this takes precedence over tier-derived OpenCode permissions.
    opencode_permission_override: str | None = None


def parse_permission_tier(
    raw: str | PermissionTier | None,
) -> PermissionTier | None:
    """Parse one permission tier string."""

    if raw is None:
        return None
    if isinstance(raw, PermissionTier):
        return raw

    normalized = raw.strip().lower()
    if not normalized:
        return None
    return _parse_permission_tier_value(normalized)


def permission_tier_from_profile(
    agent_sandbox: str | None,
    *,
    warning_logger: logging.Logger | None = None,
) -> str | None:
    if agent_sandbox is None:
        return None
    normalized = agent_sandbox.strip().lower()
    if not normalized:
        return None
    mapping = {
        "read-only": "read-only",
        "workspace-write": "workspace-write",
        "full-access": "full-access",
        "danger-full-access": "full-access",
        "unrestricted": "full-access",
    }
    resolved = mapping.get(normalized)
    if resolved is not None:
        return resolved

    sink = warning_logger or logger
    sink.warning(
        "Agent profile has unsupported sandbox '%s'; harness defaults will apply.",
        agent_sandbox.strip(),
    )
    return None


def _parse_permission_tier_value(raw: str | PermissionTier) -> PermissionTier:
    if isinstance(raw, PermissionTier):
        return raw

    normalized = raw.strip().lower()
    if not normalized:
        raise ValueError("Unsupported permission tier ''.")
    for candidate in PermissionTier:
        if candidate.value == normalized:
            return candidate
    allowed = ", ".join(item.value for item in PermissionTier)
    raise ValueError(f"Unsupported permission tier '{raw}'. Expected: {allowed}.")


def _parse_approval_value(raw: str) -> str:
    normalized = raw.strip().lower()
    if normalized in _APPROVAL_MODES:
        return normalized
    allowed = ", ".join(sorted(_APPROVAL_MODES))
    raise ValueError(f"Unsupported approval mode '{raw}'. Expected: {allowed}.")


def build_permission_config(
    tier: str | PermissionTier | None,
    *,
    approval: str = "confirm",
) -> PermissionConfig:
    """Build and validate a permission configuration."""

    return PermissionConfig(
        tier=parse_permission_tier(tier),
        approval=_parse_approval_value(approval),
    )


def _normalize_tool_name(raw: str) -> str:
    """Normalize a tool name: strip Claude-style qualifiers and lowercase.

    ``Bash(git status)`` → ``bash``, ``Read`` → ``read``.
    Tool names pass through directly — no mapping table needed since
    Claude, OpenCode, and Codex use the same lowercase names.
    """
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


def permission_flags_for_harness(
    harness_id: HarnessId,
    config: PermissionConfig,
) -> list[str]:
    """Translate one tier into harness-specific CLI flags."""

    tier = config.tier
    if config.approval == "auto":
        if harness_id == HarnessId.CLAUDE:
            return ["--dangerously-skip-permissions"]
        if harness_id == HarnessId.CODEX:
            return ["--dangerously-bypass-approvals-and-sandbox"]
        # OpenCode currently has no equivalent global bypass flag.
    if tier is None:
        return []

    if harness_id == HarnessId.CODEX:
        if tier is PermissionTier.READ_ONLY:
            return ["--sandbox", "read-only"]
        if tier is PermissionTier.WORKSPACE_WRITE:
            return ["--sandbox", "workspace-write"]
        if tier is PermissionTier.FULL_ACCESS:
            return ["--sandbox", "danger-full-access"]
        raise ValueError(f"Unsupported Codex permission tier: {tier!r}")

    # OpenCode permission controls vary by backend provider; keep default behavior for
    # safe tiers until a stable CLI surface is available.
    return []


class TieredPermissionResolver(BaseModel):
    """PermissionResolver implementation backed by one tier config."""

    model_config = ConfigDict(frozen=True)

    config: PermissionConfig

    def resolve_flags(self, harness_id: HarnessId) -> list[str]:
        return permission_flags_for_harness(harness_id, self.config)


class ExplicitToolsResolver(BaseModel):
    """PermissionResolver backed by an explicit tool allowlist.

    For harnesses that don't support fine-grained tool lists (Codex),
    falls back to tier-based flags using the provided fallback config.
    """

    model_config = ConfigDict(frozen=True)

    allowed_tools: tuple[str, ...]
    fallback_config: PermissionConfig

    def opencode_permission_json(self) -> str:
        return opencode_permission_json_for_allowed_tools(self.allowed_tools)

    def resolve_flags(self, harness_id: HarnessId) -> list[str]:
        # Codex only supports --sandbox, not per-tool allowlists.
        if harness_id == HarnessId.CODEX:
            return permission_flags_for_harness(harness_id, self.fallback_config)

        # Claude: emit explicit allowedTools list.
        if harness_id == HarnessId.CLAUDE:
            return ["--allowedTools", ",".join(self.allowed_tools)]

        # OpenCode allows per-tool permissions through OPENCODE_PERMISSION env,
        # not run CLI flags. resolve_permission_pipeline wires that env payload.
        if harness_id == HarnessId.OPENCODE:
            return []

        # Other harnesses: no fine-grained tool allowlist support.
        return []


def build_permission_resolver(
    *,
    allowed_tools: tuple[str, ...],
    permission_config: PermissionConfig,
) -> TieredPermissionResolver | ExplicitToolsResolver:
    """Pick the right resolver: explicit tools if specified, else tier-based.
    """
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
    approval: str = "confirm",
) -> tuple[PermissionConfig, TieredPermissionResolver | ExplicitToolsResolver]:
    inferred_tier = permission_tier_from_profile(sandbox)
    config = build_permission_config(inferred_tier, approval=approval)
    resolver = build_permission_resolver(
        allowed_tools=allowed_tools,
        permission_config=config,
    )
    if isinstance(resolver, ExplicitToolsResolver):
        config = config.model_copy(
            update={"opencode_permission_override": resolver.opencode_permission_json()}
        )
    return config, resolver
