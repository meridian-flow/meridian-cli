"""Codex subprocess command projection from ``CodexLaunchSpec``."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import cast

from meridian.lib.harness.launch_spec import CodexLaunchSpec
from meridian.lib.harness.projections._guards import (
    check_projection_drift as _check_projection_drift,
)
from meridian.lib.launch.launch_types import PermissionResolver



class HarnessCapabilityMismatch(ValueError):
    """Raised when requested launch semantics cannot be represented on Codex."""


_PROJECTED_FIELDS: frozenset[str] = frozenset(
    {
        "model",
        "effort",
        "prompt",
        "continue_session_id",
        "continue_fork",
        "permission_resolver",
        "extra_args",
        "interactive",
        "mcp_tools",
        "report_output_path",
    }
)

_DELEGATED_FIELDS: frozenset[str] = frozenset()

_APPROVAL_POLICY_BY_MODE: dict[str, str | None] = {
    "default": None,
    "auto": "on-request",
    "confirm": "untrusted",
    "yolo": "never",
}

_SANDBOX_MODE_BY_MODE: dict[str, str | None] = {
    "default": None,
    "read-only": "read-only",
    "workspace-write": "workspace-write",
    "danger-full-access": "danger-full-access",
}
def map_codex_approval_policy(approval_mode: str) -> str | None:
    """Map Meridian approval mode to Codex approval policy."""

    if approval_mode not in _APPROVAL_POLICY_BY_MODE:
        raise HarnessCapabilityMismatch(
            "Codex cannot express requested approval mode "
            f"'{approval_mode}' on this CLI/protocol version"
        )
    mapped = _APPROVAL_POLICY_BY_MODE[approval_mode]
    if mapped is None and approval_mode != "default":
        raise HarnessCapabilityMismatch(
            "Codex cannot express requested approval mode "
            f"'{approval_mode}' on this CLI/protocol version"
        )
    return mapped


def map_codex_sandbox_mode(sandbox_mode: str) -> str | None:
    """Map Meridian sandbox mode to Codex sandbox mode."""

    if sandbox_mode not in _SANDBOX_MODE_BY_MODE:
        raise HarnessCapabilityMismatch(
            "Codex cannot express requested sandbox mode "
            f"'{sandbox_mode}' on this CLI/protocol version"
        )
    mapped = _SANDBOX_MODE_BY_MODE[sandbox_mode]
    if mapped is None and sandbox_mode != "default":
        raise HarnessCapabilityMismatch(
            "Codex cannot express requested sandbox mode "
            f"'{sandbox_mode}' on this CLI/protocol version"
        )
    return mapped


def _coerce_permission_flags(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, tuple):
        return tuple(str(token) for token in cast("tuple[object, ...]", raw))
    if isinstance(raw, list):
        return tuple(str(token) for token in cast("list[object]", raw))
    if isinstance(raw, Iterable):
        return tuple(str(token) for token in cast("Iterable[object]", raw))
    raise TypeError(f"Permission resolver flags must be iterable, got {type(raw).__name__}")


def _strip_tool_flags_for_codex(flags: tuple[str, ...]) -> tuple[str, ...]:
    """Strip --allowedTools/--disallowedTools flags that Codex doesn't support."""
    filtered: list[str] = []
    index = 0
    while index < len(flags):
        token = flags[index]

        if token == "--allowedTools":
            index += 2
            continue
        if token.startswith("--allowedTools="):
            index += 1
            continue
        if token == "--disallowedTools":
            index += 2
            continue
        if token.startswith("--disallowedTools="):
            index += 1
            continue

        filtered.append(token)
        index += 1

    return tuple(filtered)


def project_codex_permission_flags(permission_resolver: PermissionResolver) -> tuple[str, ...]:
    """Build Codex subprocess permission flags from resolver config and hints."""

    config = permission_resolver.config
    flags: list[str] = []

    sandbox_mode = map_codex_sandbox_mode(config.sandbox)
    if sandbox_mode is not None:
        flags.extend(("--sandbox", sandbox_mode))

    approval_policy = map_codex_approval_policy(config.approval)
    if approval_policy is not None:
        flags.extend(("-c", f'approval_policy={json.dumps(approval_policy)}'))

    resolver_flags = _strip_tool_flags_for_codex(
        _coerce_permission_flags(permission_resolver.resolve_flags())
    )
    flags.extend(resolver_flags)
    return tuple(flags)


def project_codex_mcp_config_flags(mcp_tools: Iterable[str]) -> tuple[str, ...]:
    """Project ``mcp_tools`` to Codex ``-c mcp.servers.*.command=...`` flags."""

    projected: list[str] = []
    for raw_entry in mcp_tools:
        entry = raw_entry.strip()
        if not entry:
            continue
        name, separator, command = entry.partition("=")
        if not separator or not name.strip() or not command.strip():
            raise ValueError(
                "Codex mcp_tools entries must be '<name>=<command>'; "
                f"got {raw_entry!r}"
            )
        projected.extend(
            (
                "-c",
                f"mcp.servers.{name.strip()}.command={json.dumps(command.strip())}",
            )
        )
    return tuple(projected)


def project_codex_spec_to_cli_args(
    spec: CodexLaunchSpec,
    *,
    base_command: tuple[str, ...],
) -> list[str]:
    """Project one ``CodexLaunchSpec`` into an ordered subprocess command list."""

    command: list[str] = list(base_command)

    harness_session_id = (spec.continue_session_id or "").strip()
    if spec.interactive:
        guarded_prompt = spec.prompt
        if guarded_prompt and not harness_session_id:
            guarded_prompt = f"{guarded_prompt}\n\nDO NOT DO ANYTHING. WAIT FOR USER INPUT."
    else:
        guarded_prompt = "-"

    if spec.model is not None:
        command.extend(("--model", spec.model))

    normalized_effort = (spec.effort or "").strip()
    if normalized_effort:
        command.extend(("-c", f"model_reasoning_effort={json.dumps(normalized_effort)}"))

    command.extend(project_codex_permission_flags(spec.permission_resolver))
    command.extend(project_codex_mcp_config_flags(spec.mcp_tools))

    if harness_session_id:
        command.extend(("resume", harness_session_id))

    command.extend(spec.extra_args)

    if not spec.interactive and spec.report_output_path:
        command.extend(("-o", spec.report_output_path))

    if guarded_prompt:
        command.append(guarded_prompt)

    return command


_check_projection_drift(
    CodexLaunchSpec,
    projected=_PROJECTED_FIELDS,
    delegated=_DELEGATED_FIELDS,
)


__all__ = [
    "_DELEGATED_FIELDS",
    "_PROJECTED_FIELDS",
    "HarnessCapabilityMismatch",
    "_check_projection_drift",
    "map_codex_approval_policy",
    "map_codex_sandbox_mode",
    "project_codex_mcp_config_flags",
    "project_codex_permission_flags",
    "project_codex_spec_to_cli_args",
]
