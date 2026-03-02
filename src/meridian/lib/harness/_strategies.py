"""Shared strategy-driven command builder for harness adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
from enum import StrEnum
from typing import cast

from meridian.lib.harness.adapter import McpConfig, PermissionResolver, SpawnParams
from meridian.lib.types import HarnessId


class FlagEffect(StrEnum):
    """Command-building effect for one SpawnParams field."""

    CLI_FLAG = "cli_flag"
    TRANSFORM = "transform"
    DROP = "drop"


type StrategyTransform = Callable[[object, list[str]], None]


@dataclass(frozen=True, slots=True)
class FlagStrategy:
    """Mapping rule for how one SpawnParams field is applied to CLI args."""

    effect: FlagEffect
    cli_flag: str | None = None
    transform: StrategyTransform | None = None


class PromptMode(StrEnum):
    """How prompt text is placed in the harness command."""

    FLAG = "flag"
    POSITIONAL = "positional"


type StrategyMap = dict[str, FlagStrategy]


_SKIP_FIELDS = frozenset(
    {"prompt", "extra_args", "repo_root", "mcp_tools", "adhoc_agent_json"}
)


def _append_cli_flag(*, args: list[str], flag: str, value: object) -> None:
    if isinstance(value, tuple):
        tuple_value = cast("tuple[object, ...]", value)
        if not tuple_value:
            return
        args.extend([flag, ",".join(str(item) for item in tuple_value)])
        return
    args.extend([flag, str(value)])


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _dedupe_preserving_order(items: list[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return tuple(ordered)


def _merge_claude_allowed_tools(
    flags: list[str],
    mcp_allowed_tools: tuple[str, ...],
) -> list[str]:
    if not mcp_allowed_tools:
        return flags

    preserved: list[str] = []
    permission_allowed_tools: list[str] = []
    index = 0
    while index < len(flags):
        token = flags[index]
        if token != "--allowedTools":
            preserved.append(token)
            index += 1
            continue
        if index + 1 >= len(flags):
            preserved.append(token)
            index += 1
            continue
        permission_allowed_tools.extend(_split_csv(flags[index + 1]))
        index += 2

    merged_allowed_tools = _dedupe_preserving_order(
        [*permission_allowed_tools, *list(mcp_allowed_tools)]
    )
    if not merged_allowed_tools:
        return preserved
    preserved.extend(["--allowedTools", ",".join(merged_allowed_tools)])
    return preserved


def build_harness_command(
    *,
    base_command: tuple[str, ...],
    prompt_mode: PromptMode,
    run: SpawnParams,
    strategies: StrategyMap,
    perms: PermissionResolver,
    harness_id: HarnessId,
    mcp_config: McpConfig | None = None,
) -> list[str]:
    """Build one harness command using field strategies."""

    strategy_args: list[str] = []
    for run_field in fields(SpawnParams):
        field_name = run_field.name
        if field_name in _SKIP_FIELDS:
            continue

        strategy = strategies.get(field_name)
        if strategy is None:
            continue

        value = getattr(run, field_name)
        if value is None:
            continue

        if strategy.effect is FlagEffect.CLI_FLAG:
            if strategy.cli_flag is None:
                raise ValueError(f"CLI_FLAG strategy for '{field_name}' requires cli_flag.")
            _append_cli_flag(args=strategy_args, flag=strategy.cli_flag, value=value)
            continue

        if strategy.effect is FlagEffect.TRANSFORM:
            if strategy.transform is None:
                raise ValueError(f"TRANSFORM strategy for '{field_name}' requires transform.")
            strategy.transform(value, strategy_args)
            continue

    command = list(base_command)
    if prompt_mode is PromptMode.FLAG:
        command.append(run.prompt)
    command.extend(strategy_args)
    permission_flags = perms.resolve_flags(harness_id)
    if mcp_config is not None and harness_id == HarnessId("claude"):
        permission_flags = _merge_claude_allowed_tools(
            permission_flags,
            mcp_config.claude_allowed_tools,
        )
    command.extend(permission_flags)
    if mcp_config is not None:
        command.extend(mcp_config.command_args)
    if prompt_mode is PromptMode.POSITIONAL:
        command.extend(run.extra_args)
        command.append(run.prompt)
        return command
    command.extend(run.extra_args)
    return command
