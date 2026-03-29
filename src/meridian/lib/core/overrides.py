"""Shared runtime override fields and layer resolution helpers."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, field_validator

if TYPE_CHECKING:
    from meridian.lib.catalog.agent import AgentProfile
    from meridian.lib.config.settings import MeridianConfig
    from meridian.lib.launch.types import LaunchRequest
    from meridian.lib.ops.spawn.models import SpawnCreateInput

_AUTOCOMPACT_MIN = 1
_AUTOCOMPACT_MAX = 100

KNOWN_THINKING_VALUES = frozenset({"low", "medium", "high", "xhigh"})
KNOWN_SANDBOX_VALUES = frozenset(
    {
        "read-only",
        "workspace-write",
        "full-access",
        "danger-full-access",
        "unrestricted",
    }
)
KNOWN_APPROVAL_VALUES = frozenset({"default", "confirm", "auto", "yolo"})


def _parse_env_int(raw_value: str, *, env_name: str) -> int:
    try:
        return int(raw_value.strip())
    except ValueError as error:
        raise ValueError(
            f"Invalid environment override '{env_name}': expected int, got {raw_value!r}."
        ) from error


def _parse_env_float(raw_value: str, *, env_name: str) -> float:
    try:
        return float(raw_value.strip())
    except ValueError as error:
        raise ValueError(
            f"Invalid environment override '{env_name}': expected float, got {raw_value!r}."
        ) from error


def _read_env_string(env_name: str) -> str | None:
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    return normalized


def _normalize_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


class RuntimeOverrides(BaseModel):
    """Fields that can be set at any config layer."""

    model_config = ConfigDict(frozen=True)

    model: str | None = None
    harness: str | None = None
    thinking: str | None = None
    sandbox: str | None = None
    approval: str | None = None
    autocompact: int | None = None
    timeout: float | None = None
    budget: float | None = None
    max_turns: int | None = None

    @field_validator("thinking")
    @classmethod
    def _validate_thinking(cls, value: str | None) -> str | None:
        normalized = _normalize_optional_string(value)
        if normalized is None:
            return None
        if normalized not in KNOWN_THINKING_VALUES:
            raise ValueError(
                "Invalid runtime override 'thinking': expected one of "
                f"{sorted(KNOWN_THINKING_VALUES)}, got {value!r}."
            )
        return normalized

    @field_validator("sandbox")
    @classmethod
    def _validate_sandbox(cls, value: str | None) -> str | None:
        normalized = _normalize_optional_string(value)
        if normalized is None:
            return None
        if normalized not in KNOWN_SANDBOX_VALUES:
            raise ValueError(
                "Invalid runtime override 'sandbox': expected one of "
                f"{sorted(KNOWN_SANDBOX_VALUES)}, got {value!r}."
            )
        return normalized

    @field_validator("approval")
    @classmethod
    def _validate_approval(cls, value: str | None) -> str | None:
        normalized = _normalize_optional_string(value)
        if normalized is None:
            return None
        if normalized not in KNOWN_APPROVAL_VALUES:
            raise ValueError(
                "Invalid runtime override 'approval': expected one of "
                f"{sorted(KNOWN_APPROVAL_VALUES)}, got {value!r}."
            )
        return normalized

    @field_validator("autocompact")
    @classmethod
    def _validate_autocompact(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not (_AUTOCOMPACT_MIN <= value <= _AUTOCOMPACT_MAX):
            raise ValueError(
                "Invalid runtime override 'autocompact': expected int between "
                f"{_AUTOCOMPACT_MIN} and {_AUTOCOMPACT_MAX}, got {value!r}."
            )
        return value

    @field_validator("timeout", "budget")
    @classmethod
    def _validate_positive_float(cls, value: float | None, info: object) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or value <= 0:
            field_name = getattr(info, "field_name", "value")
            raise ValueError(
                f"Invalid runtime override '{field_name}': expected float > 0, got {value!r}."
            )
        return value

    @field_validator("max_turns")
    @classmethod
    def _validate_max_turns(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or value <= 0:
            raise ValueError(
                f"Invalid runtime override 'max_turns': expected int > 0, got {value!r}."
            )
        return value

    @classmethod
    def from_env(cls) -> RuntimeOverrides:
        autocompact_raw = _read_env_string("MERIDIAN_AUTOCOMPACT")
        timeout_raw = _read_env_string("MERIDIAN_TIMEOUT")
        budget_raw = _read_env_string("MERIDIAN_BUDGET")
        max_turns_raw = _read_env_string("MERIDIAN_MAX_TURNS")
        return cls(
            model=_read_env_string("MERIDIAN_MODEL"),
            harness=_read_env_string("MERIDIAN_HARNESS"),
            thinking=_read_env_string("MERIDIAN_THINKING"),
            sandbox=_read_env_string("MERIDIAN_SANDBOX"),
            approval=_read_env_string("MERIDIAN_APPROVAL"),
            autocompact=(
                _parse_env_int(autocompact_raw, env_name="MERIDIAN_AUTOCOMPACT")
                if autocompact_raw is not None
                else None
            ),
            timeout=(
                _parse_env_float(timeout_raw, env_name="MERIDIAN_TIMEOUT")
                if timeout_raw is not None
                else None
            ),
            budget=(
                _parse_env_float(budget_raw, env_name="MERIDIAN_BUDGET")
                if budget_raw is not None
                else None
            ),
            max_turns=(
                _parse_env_int(max_turns_raw, env_name="MERIDIAN_MAX_TURNS")
                if max_turns_raw is not None
                else None
            ),
        )

    @classmethod
    def from_agent_profile(cls, profile: AgentProfile | None) -> RuntimeOverrides:
        if profile is None:
            return cls()
        return cls(
            model=_normalize_optional_string(profile.model),
            harness=_normalize_optional_string(profile.harness),
            thinking=_normalize_optional_string(profile.thinking),
            sandbox=_normalize_optional_string(profile.sandbox),
            approval=_normalize_optional_string(profile.approval),
            autocompact=profile.autocompact,
        )

    @classmethod
    def from_config(cls, config: MeridianConfig | None) -> RuntimeOverrides:
        if config is None:
            return cls()
        primary = config.primary
        return cls(
            model=primary.model,
            harness=primary.harness,
            thinking=primary.thinking,
            sandbox=primary.sandbox,
            approval=primary.approval,
            autocompact=primary.autocompact,
            timeout=primary.timeout,
            budget=primary.budget,
            max_turns=primary.max_turns,
        )

    @classmethod
    def from_spawn_input(cls, payload: SpawnCreateInput) -> RuntimeOverrides:
        return cls(
            model=_normalize_optional_string(payload.model),
            harness=_normalize_optional_string(payload.harness),
            thinking=_normalize_optional_string(payload.thinking),
            sandbox=_normalize_optional_string(payload.sandbox),
            approval=_normalize_optional_string(payload.approval),
            autocompact=payload.autocompact,
            timeout=payload.timeout,
        )

    @classmethod
    def from_launch_request(cls, request: LaunchRequest) -> RuntimeOverrides:
        return cls(
            model=_normalize_optional_string(request.model),
            harness=_normalize_optional_string(request.harness),
            thinking=_normalize_optional_string(request.thinking),
            sandbox=_normalize_optional_string(request.sandbox),
            approval=request.approval if request.approval != "default" else None,
            autocompact=request.autocompact,
            timeout=request.timeout,
        )


def resolve(*layers: RuntimeOverrides) -> RuntimeOverrides:
    """Merge layers with first-non-none precedence."""

    resolved: dict[str, object] = {}
    for field_name in RuntimeOverrides.model_fields:
        for layer in layers:
            value = getattr(layer, field_name)
            if value is not None:
                resolved[field_name] = value
                break
    return RuntimeOverrides.model_validate(resolved)


__all__ = [
    "KNOWN_APPROVAL_VALUES",
    "KNOWN_SANDBOX_VALUES",
    "KNOWN_THINKING_VALUES",
    "RuntimeOverrides",
    "resolve",
]
