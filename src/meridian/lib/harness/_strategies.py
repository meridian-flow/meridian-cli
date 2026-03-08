"""Shared strategy-driven command builder for harness adapters."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import cast

from pydantic import BaseModel, ConfigDict

from meridian.lib.harness.adapter import McpConfig, PermissionResolver, SpawnParams
from meridian.lib.types import HarnessId


class FlagEffect(StrEnum):
    """Command-building effect for one SpawnParams field."""

    CLI_FLAG = "cli_flag"
    TRANSFORM = "transform"
    DROP = "drop"


type StrategyTransform = Callable[[object, list[str]], None]


class FlagStrategy(BaseModel):
    """Mapping rule for how one SpawnParams field is applied to CLI args."""

    model_config = ConfigDict(frozen=True)

    effect: FlagEffect
    cli_flag: str | None = None
    transform: StrategyTransform | None = None


class PromptMode(StrEnum):
    """How prompt text is placed in the harness command."""

    FLAG = "flag"
    POSITIONAL = "positional"


type StrategyMap = dict[str, FlagStrategy]


_SKIP_FIELDS = frozenset(
    {"prompt", "extra_args", "repo_root", "mcp_tools", "adhoc_agent_json", "interactive", "report_output_path"}
)


def _append_cli_flag(*, args: list[str], flag: str, value: object) -> None:
    if isinstance(value, tuple):
        tuple_value = cast("tuple[object, ...]", value)
        if not tuple_value:
            return
        args.extend([flag, ",".join(str(item) for item in tuple_value)])
        return
    args.extend([flag, str(value)])


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

    all_fields = set(SpawnParams.model_fields)
    unmapped = all_fields - set(strategies.keys()) - _SKIP_FIELDS
    if unmapped:
        raise ValueError(
            f"SpawnParams fields missing strategy mappings: {', '.join(sorted(unmapped))}. "
            f"Add a FlagStrategy (use DROP to ignore) for each."
        )

    strategy_args: list[str] = []
    for field_name in SpawnParams.model_fields:
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
    if prompt_mode is PromptMode.FLAG and run.prompt:
        command.append(run.prompt)
    command.extend(strategy_args)
    permission_flags = perms.resolve_flags(harness_id)
    command.extend(permission_flags)
    if mcp_config is not None:
        command.extend(mcp_config.command_args)
    if prompt_mode is PromptMode.POSITIONAL:
        command.extend(run.extra_args)
        if run.prompt:
            command.append(run.prompt)
        return command
    command.extend(run.extra_args)
    return command
