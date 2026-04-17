"""OpenCode subprocess command projection from ``OpenCodeLaunchSpec``."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

from meridian.lib.harness.ids import HarnessId
from meridian.lib.harness.launch_spec import OpenCodeLaunchSpec
from meridian.lib.harness.projections._guards import (
    check_projection_drift as _check_projection_drift,
)
from meridian.lib.harness.projections.permission_flags import resolve_permission_flags

logger = logging.getLogger(__name__)


class HarnessCapabilityMismatch(ValueError):
    """Raised when requested launch semantics cannot be represented on OpenCode."""


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
        "agent_name",
        "skills",
    }
)

_DELEGATED_FIELDS: frozenset[str] = frozenset()


def _normalized_nonempty(values: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        token = value.strip()
        if token:
            normalized.append(token)
    return tuple(normalized)


_MANAGED_FLAG_ALIASES: dict[str, tuple[str, ...]] = {
    "--model": ("--model", "-m"),
    "--variant": ("--variant",),
    "--agent": ("--agent",),
    "--session": ("--session", "-s", "--continue", "-c"),
    "--fork": ("--fork",),
}


def _has_flag(args: Sequence[str], flag: str) -> bool:
    return any(token == flag or token.startswith(f"{flag}=") for token in args)


def _log_collision_if_needed(
    *,
    managed_flag: str,
    has_managed_value: bool,
    passthrough_tail: tuple[str, ...],
) -> None:
    if not has_managed_value:
        return

    aliases = _MANAGED_FLAG_ALIASES.get(managed_flag, (managed_flag,))
    if not any(_has_flag(passthrough_tail, alias) for alias in aliases):
        return

    logger.debug(
        "OpenCode projection known managed flag %s also present in extra_args; "
        "user tail value wins by last-wins semantics",
        managed_flag,
    )


def project_opencode_spec_to_cli_args(
    spec: OpenCodeLaunchSpec,
    *,
    base_command: tuple[str, ...],
) -> list[str]:
    """Project one ``OpenCodeLaunchSpec`` into an ordered subprocess command list."""

    projected_mcp_tools = _normalized_nonempty(spec.mcp_tools)
    if projected_mcp_tools:
        raise HarnessCapabilityMismatch(
            "OpenCode subprocess does not support per-spawn mcp_tools; "
            "use streaming transport (opencode serve) for MCP session payloads."
        )

    if spec.skills:
        logger.debug(
            "OpenCode subprocess received spec.skills but has no native skills flag; "
            "skills must be delivered by prompt injection or streaming payload"
        )

    command: list[str] = list(base_command)

    if spec.model is not None:
        command.extend(("--model", spec.model))

    normalized_effort = (spec.effort or "").strip()
    if normalized_effort:
        command.extend(("--variant", normalized_effort))

    if spec.agent_name:
        command.extend(("--agent", spec.agent_name))

    harness_session_id = (spec.continue_session_id or "").strip()
    has_continue_session = bool(harness_session_id)
    has_continue_fork = has_continue_session and spec.continue_fork
    passthrough_tail = spec.extra_args

    _log_collision_if_needed(
        managed_flag="--model",
        has_managed_value=spec.model is not None,
        passthrough_tail=passthrough_tail,
    )
    _log_collision_if_needed(
        managed_flag="--variant",
        has_managed_value=bool(normalized_effort),
        passthrough_tail=passthrough_tail,
    )
    _log_collision_if_needed(
        managed_flag="--agent",
        has_managed_value=bool(spec.agent_name),
        passthrough_tail=passthrough_tail,
    )
    _log_collision_if_needed(
        managed_flag="--session",
        has_managed_value=has_continue_session,
        passthrough_tail=passthrough_tail,
    )
    _log_collision_if_needed(
        managed_flag="--fork",
        has_managed_value=has_continue_fork,
        passthrough_tail=passthrough_tail,
    )

    command.extend(resolve_permission_flags(spec.permission_resolver, HarnessId.OPENCODE))
    command.extend(passthrough_tail)

    if spec.interactive:
        if spec.prompt:
            command.extend(("--prompt", spec.prompt))
    else:
        command.append("-")

    if has_continue_session:
        command.extend(("--session", harness_session_id))
        if has_continue_fork:
            command.append("--fork")

    return command


_check_projection_drift(
    OpenCodeLaunchSpec,
    projected=_PROJECTED_FIELDS,
    delegated=_DELEGATED_FIELDS,
)


__all__ = [
    "_DELEGATED_FIELDS",
    "_PROJECTED_FIELDS",
    "HarnessCapabilityMismatch",
    "_check_projection_drift",
    "project_opencode_spec_to_cli_args",
]
