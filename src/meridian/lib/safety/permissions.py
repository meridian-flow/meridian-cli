"""Permission configuration and harness-flag translation."""

import json
import logging

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.overrides import KNOWN_APPROVAL_VALUES
from meridian.lib.core.types import HarnessId

logger = logging.getLogger(__name__)


_APPROVAL_MODES = KNOWN_APPROVAL_VALUES


class PermissionConfig(BaseModel):
    """Resolved permission configuration for one run."""

    model_config = ConfigDict(frozen=True)

    sandbox: str | None = None
    approval: str = "default"
    # Optional OpenCode permission map JSON derived from explicit allowed_tools.
    # When set, this takes precedence over sandbox-derived OpenCode permissions.
    opencode_permission_override: str | None = None


def _parse_approval_value(raw: str) -> str:
    normalized = raw.strip().lower()
    if normalized in _APPROVAL_MODES:
        return normalized
    allowed = ", ".join(sorted(_APPROVAL_MODES))
    raise ValueError(f"Unsupported approval mode '{raw}'. Expected: {allowed}.")


def build_permission_config(
    sandbox: str | None,
    *,
    approval: str = "default",
) -> PermissionConfig:
    """Build and validate a permission configuration."""

    normalized = sandbox.strip().lower() if sandbox else None
    return PermissionConfig(
        sandbox=normalized or None,
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


def opencode_permission_json_for_disallowed_tools(disallowed_tools: tuple[str, ...]) -> str:
    """Build OpenCode permission JSON from an explicit disallowed-tools tuple."""

    permissions: dict[str, str] = {"*": "allow"}
    for raw_tool in disallowed_tools:
        normalized = _normalize_tool_name(raw_tool)
        if not normalized:
            continue
        permissions[normalized] = "deny"
    return json.dumps(permissions, sort_keys=True, separators=(",", ":"))


def permission_flags_for_harness(
    harness_id: HarnessId,
    config: PermissionConfig,
) -> list[str]:
    """Translate sandbox + approval into harness-specific CLI flags."""

    sandbox = config.sandbox
    approval = config.approval

    # --- approval-level flags (take precedence over sandbox) ---
    if approval == "yolo":
        if harness_id == HarnessId.CLAUDE:
            return ["--dangerously-skip-permissions"]
        if harness_id == HarnessId.CODEX:
            return ["--dangerously-bypass-approvals-and-sandbox"]
        # OpenCode currently has no equivalent global bypass flag.
    elif approval == "auto":
        if harness_id == HarnessId.CLAUDE:
            return ["--permission-mode", "acceptEdits"]
        if harness_id == HarnessId.CODEX:
            return ["--full-auto"]
    elif approval == "confirm":
        if harness_id == HarnessId.CLAUDE:
            return ["--permission-mode", "default"]
        if harness_id == HarnessId.CODEX:
            return ["--ask-for-approval", "untrusted"]
    # "default" or None → no approval flags, fall through to sandbox logic.

    if sandbox is None:
        return []

    if harness_id == HarnessId.CODEX:
        return ["--sandbox", sandbox]

    # Other harnesses: no sandbox flag support yet.
    return []


class TieredPermissionResolver(BaseModel):
    """PermissionResolver implementation backed by one sandbox config."""

    model_config = ConfigDict(frozen=True)

    config: PermissionConfig

    def resolve_flags(self, harness_id: HarnessId) -> list[str]:
        return permission_flags_for_harness(harness_id, self.config)


class ExplicitToolsResolver(BaseModel):
    """PermissionResolver backed by an explicit tool allowlist.

    For harnesses that don't support fine-grained tool lists (Codex),
    falls back to sandbox-based flags using the provided fallback config.
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


class DisallowedToolsResolver(BaseModel):
    """PermissionResolver backed by an explicit tool denylist."""

    model_config = ConfigDict(frozen=True)

    disallowed_tools: tuple[str, ...]
    fallback_config: PermissionConfig

    def opencode_permission_json(self) -> str:
        return opencode_permission_json_for_disallowed_tools(self.disallowed_tools)

    def resolve_flags(self, harness_id: HarnessId) -> list[str]:
        # Codex only supports --sandbox, not per-tool denylists.
        if harness_id == HarnessId.CODEX:
            logger.warning(
                "Codex does not support disallowed-tools; falling back to sandbox/approval flags."
            )
            return permission_flags_for_harness(harness_id, self.fallback_config)

        # Claude: emit explicit disallowedTools list.
        if harness_id == HarnessId.CLAUDE:
            return ["--disallowedTools", ",".join(self.disallowed_tools)]

        # OpenCode allows per-tool permissions through OPENCODE_PERMISSION env,
        # not run CLI flags. resolve_permission_pipeline wires that env payload.
        if harness_id == HarnessId.OPENCODE:
            return []

        # Other harnesses: no fine-grained tool denylist support.
        return []


class CombinedToolsResolver(BaseModel):
    """PermissionResolver that selects allowlist or denylist tool controls."""

    model_config = ConfigDict(frozen=True)

    allowlist: ExplicitToolsResolver | None = None
    denylist: DisallowedToolsResolver | None = None

    def resolve_flags(self, harness_id: HarnessId) -> list[str]:
        if self.allowlist is not None:
            return self.allowlist.resolve_flags(harness_id)
        if self.denylist is not None:
            return self.denylist.resolve_flags(harness_id)
        return []

    def opencode_permission_json(self) -> str | None:
        if self.allowlist is not None:
            return self.allowlist.opencode_permission_json()
        if self.denylist is not None:
            return self.denylist.opencode_permission_json()
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
    """Pick the right resolver: explicit tools if specified, else sandbox-based."""
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
    if allowed_tools and disallowed_tools:
        logger.warning(
            "Both tools (allowlist) and disallowed-tools (denylist) are set; "
            "using allowlist and ignoring denylist."
        )
    resolver = build_permission_resolver(
        allowed_tools=allowed_tools,
        disallowed_tools=disallowed_tools,
        permission_config=config,
    )
    if isinstance(resolver, (ExplicitToolsResolver, DisallowedToolsResolver)):
        config = config.model_copy(
            update={"opencode_permission_override": resolver.opencode_permission_json()}
        )
    elif isinstance(resolver, CombinedToolsResolver):
        opencode_override = resolver.opencode_permission_json()
        if opencode_override is not None:
            config = config.model_copy(update={"opencode_permission_override": opencode_override})
    return config, resolver
