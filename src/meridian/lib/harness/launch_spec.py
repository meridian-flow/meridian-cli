"""Resolved launch spec models for harness adapters."""

from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Protocol, cast

from meridian.lib.harness.adapter import SpawnParams, SubprocessHarness
from meridian.lib.harness.ids import HarnessId
from meridian.lib.launch.launch_types import ResolvedLaunchSpec


class ClaudeLaunchSpec(ResolvedLaunchSpec):
    """Claude-specific resolved launch spec."""

    agent_name: str | None = None
    agents_payload: str | None = None
    appended_system_prompt: str | None = None


class CodexLaunchSpec(ResolvedLaunchSpec):
    """Codex-specific resolved launch spec."""

    report_output_path: str | None = None


class OpenCodeLaunchSpec(ResolvedLaunchSpec):
    """OpenCode-specific resolved launch spec."""

    agent_name: str | None = None
    skills: tuple[str, ...] = ()


class HarnessBundle(Protocol):
    """Minimal bundle contract needed by spawn-params accounting tests."""

    adapter: SubprocessHarness


_PHASE2_ADAPTER_HANDLED_FIELDS: frozenset[str] = frozenset(
    {
        "prompt",
        "model",
        "effort",
        "skills",
        "agent",
        "adhoc_agent_payload",
        "extra_args",
        "repo_root",
        "mcp_tools",
        "interactive",
        "continue_harness_session_id",
        "continue_fork",
        "appended_system_prompt",
        "report_output_path",
    }
)

_REGISTRY: dict[HarnessId, HarnessBundle] = cast(
    "dict[HarnessId, HarnessBundle]",
    {
        HarnessId.CLAUDE: SimpleNamespace(
            adapter=SimpleNamespace(handled_fields=_PHASE2_ADAPTER_HANDLED_FIELDS)
        ),
        HarnessId.CODEX: SimpleNamespace(
            adapter=SimpleNamespace(handled_fields=_PHASE2_ADAPTER_HANDLED_FIELDS)
        ),
        HarnessId.OPENCODE: SimpleNamespace(
            adapter=SimpleNamespace(handled_fields=_PHASE2_ADAPTER_HANDLED_FIELDS)
        ),
    },
)

# Derived from SpawnParams for error reporting; authoritative check is per-adapter union.
_SPEC_HANDLED_FIELDS: frozenset[str] = frozenset(SpawnParams.model_fields)


def _enforce_spawn_params_accounting(
    registry: Mapping[HarnessId, HarnessBundle] | None = None,
) -> None:
    reg = registry if registry is not None else _REGISTRY
    expected = set(SpawnParams.model_fields)
    union: set[str] = set()
    per_adapter: dict[HarnessId, frozenset[str]] = {}
    for harness_id, bundle in reg.items():
        handled = frozenset(bundle.adapter.handled_fields)
        per_adapter[harness_id] = handled
        union |= handled
    missing = expected - union
    stale = union - expected
    if missing or stale:
        raise ImportError(
            "SpawnParams cross-adapter accounting drift. "
            f"Missing (no adapter claims these): {sorted(missing)}. "
            f"Stale (claimed but not on SpawnParams): {sorted(stale)}. "
            f"Per-adapter handled_fields: "
            f"{ {h.value: sorted(f) for h, f in per_adapter.items()} }"
        )


_enforce_spawn_params_accounting()


__all__ = [
    "_REGISTRY",
    "_SPEC_HANDLED_FIELDS",
    "ClaudeLaunchSpec",
    "CodexLaunchSpec",
    "HarnessBundle",
    "OpenCodeLaunchSpec",
    "ResolvedLaunchSpec",
    "_enforce_spawn_params_accounting",
]
