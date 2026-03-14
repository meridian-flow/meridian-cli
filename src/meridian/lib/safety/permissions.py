"""Permission tiers and harness-flag translation."""


import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.types import HarnessId


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


def permission_tier_from_profile(agent_sandbox: str | None) -> str | None:
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
    return mapping.get(normalized)


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


def _claude_allowed_tools(tier: PermissionTier) -> tuple[str, ...]:
    read_only = (
        "Read",
        "Glob",
        "Grep",
        "Bash(git status)",
        "Bash(git log)",
        "Bash(git diff)",
    )
    workspace_write = (
        *read_only,
        "Edit",
        "Write",
        "Bash(git add)",
        "Bash(git commit)",
    )
    full_access = (
        *workspace_write,
        "WebFetch",
        "WebSearch",
        "Bash",
    )
    if tier is PermissionTier.READ_ONLY:
        return read_only
    if tier is PermissionTier.WORKSPACE_WRITE:
        return workspace_write
    if tier is PermissionTier.FULL_ACCESS:
        return full_access
    raise ValueError(f"Unsupported Claude permission tier: {tier!r}")


def opencode_permission_json(tier: PermissionTier) -> str:
    """Build OpenCode permission JSON from one safety tier."""

    if tier is PermissionTier.READ_ONLY:
        permissions = {
            "*": "deny",
            "read": "allow",
            "grep": "allow",
            "glob": "allow",
            "list": "allow",
        }
    elif tier is PermissionTier.WORKSPACE_WRITE:
        permissions = {
            "*": "deny",
            "read": "allow",
            "grep": "allow",
            "glob": "allow",
            "list": "allow",
            "edit": "allow",
            "bash": "deny",
        }
    elif tier is PermissionTier.FULL_ACCESS:
        permissions = {"*": "allow"}
    else:  # pragma: no cover - enum exhaustive guard
        raise ValueError(f"Unsupported OpenCode permission tier: {tier!r}")

    return json.dumps(permissions, sort_keys=True, separators=(",", ":"))


def permission_flags_for_harness(
    harness_id: HarnessId,
    config: PermissionConfig,
) -> list[str]:
    """Translate one tier into harness-specific CLI flags."""

    tier = config.tier
    if config.approval == "auto":
        if harness_id == HarnessId("claude"):
            return ["--dangerously-skip-permissions"]
        if harness_id == HarnessId("codex"):
            return ["--dangerously-bypass-approvals-and-sandbox"]
        # OpenCode currently has no equivalent global bypass flag.
    if tier is None:
        return []

    if harness_id == HarnessId("claude"):
        return ["--allowedTools", ",".join(_claude_allowed_tools(tier))]

    if harness_id == HarnessId("codex"):
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

    def resolve_flags(self, harness_id: HarnessId) -> list[str]:
        # Codex only supports --sandbox, not per-tool allowlists.
        if harness_id == HarnessId("codex"):
            return permission_flags_for_harness(harness_id, self.fallback_config)

        # Claude: emit explicit allowedTools list.
        if harness_id == HarnessId("claude"):
            return ["--allowedTools", ",".join(self.allowed_tools)]

        # OpenCode / others: no fine-grained tool allowlist support yet.
        # The tier-based path also returns [] for OpenCode (permissions are
        # applied via env vars, not CLI flags), so no fallback is needed here.
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
