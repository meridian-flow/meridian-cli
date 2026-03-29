"""Structural convention tests: RuntimeOverrides field coverage across all config layers."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def _env_override(name: str, value: str) -> Iterator[None]:
    """Temporarily set an environment variable."""
    old = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


@contextmanager
def _env_overrides(overrides: dict[str, str]) -> Iterator[None]:
    """Temporarily set multiple environment variables."""
    old_values: dict[str, str | None] = {}
    for name, value in overrides.items():
        old_values[name] = os.environ.get(name)
        os.environ[name] = value
    try:
        yield
    finally:
        for name in overrides:
            if old_values[name] is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old_values[name]  # type: ignore[assignment]


# Map field names to valid test values
_TEST_VALUES: dict[str, str] = {
    "model": "test-model",
    "harness": "claude",
    "thinking": "high",
    "sandbox": "full-access",
    "approval": "auto",
    "autocompact": "50",
    "timeout": "30.0",
    "budget": "5.0",
    "max_turns": "10",
}


def test_every_field_has_env_var() -> None:
    """Every RuntimeOverrides field is readable from MERIDIAN_<UPPER_SNAKE> env."""
    from meridian.lib.core.overrides import RuntimeOverrides

    for field_name in RuntimeOverrides.model_fields:
        env_name = f"MERIDIAN_{field_name.upper()}"
        test_value = _TEST_VALUES[field_name]
        with _env_override(env_name, test_value):
            result = RuntimeOverrides.from_env()
            assert getattr(result, field_name) is not None, (
                f"RuntimeOverrides.from_env() did not read {env_name} for field '{field_name}'"
            )


def test_every_field_has_config_key() -> None:
    """Every RuntimeOverrides field is extractable from PrimaryConfig."""
    from meridian.lib.config.settings import PrimaryConfig
    from meridian.lib.core.overrides import RuntimeOverrides

    config_fields = set(PrimaryConfig.model_fields.keys())

    for field_name in RuntimeOverrides.model_fields:
        assert field_name in config_fields, (
            f"RuntimeOverrides field '{field_name}' has no matching PrimaryConfig field. "
            f"Add it to PrimaryConfig or document the exclusion."
        )


def test_every_field_has_spawn_cli_flag() -> None:
    """Every RuntimeOverrides field is settable via SpawnCreateInput."""
    from meridian.lib.core.overrides import RuntimeOverrides
    from meridian.lib.ops.spawn.models import SpawnCreateInput

    input_fields = set(SpawnCreateInput.model_fields.keys())
    # Fields not expected on SpawnCreateInput (no consumer in spawn path)
    SPAWN_EXCLUDED = {
        "budget",     # No --budget flag on spawn yet; needs wiring before CLI exposure
        "max_turns",  # No --max-turns flag on spawn yet; needs wiring before CLI exposure
    }

    for field_name in RuntimeOverrides.model_fields:
        if field_name in SPAWN_EXCLUDED:
            continue
        assert field_name in input_fields, (
            f"RuntimeOverrides field '{field_name}' has no matching SpawnCreateInput field. "
            f"Add it or document the exclusion in SPAWN_EXCLUDED."
        )


def test_every_field_has_primary_cli_flag() -> None:
    """Every RuntimeOverrides field with a consumer has a LaunchRequest field."""
    from meridian.lib.core.overrides import RuntimeOverrides
    from meridian.lib.launch.types import LaunchRequest

    request_fields = set(LaunchRequest.model_fields.keys())
    # Fields not expected on LaunchRequest (no consumer in primary pipeline)
    PRIMARY_EXCLUDED = {
        "budget",     # No --budget flag on primary yet; needs wiring before CLI exposure
        "max_turns",  # No --max-turns flag on primary yet; needs wiring before CLI exposure
    }

    for field_name in RuntimeOverrides.model_fields:
        if field_name in PRIMARY_EXCLUDED:
            continue
        assert field_name in request_fields, (
            f"RuntimeOverrides field '{field_name}' has no matching LaunchRequest field. "
            f"Add it or document the exclusion in PRIMARY_EXCLUDED."
        )


def test_from_env_round_trip() -> None:
    """from_env reads all fields correctly."""
    from meridian.lib.core.overrides import RuntimeOverrides

    env_values = {f"MERIDIAN_{k.upper()}": v for k, v in _TEST_VALUES.items()}
    with _env_overrides(env_values):
        result = RuntimeOverrides.from_env()
        for field_name in RuntimeOverrides.model_fields:
            assert getattr(result, field_name) is not None, (
                f"from_env() did not populate '{field_name}'"
            )


def test_from_config_round_trip() -> None:
    """from_config reads all 9 RuntimeOverrides fields from PrimaryConfig."""
    from meridian.lib.config.settings import MeridianConfig, PrimaryConfig
    from meridian.lib.core.overrides import RuntimeOverrides

    primary = PrimaryConfig(
        model="test-model",
        harness="claude",
        thinking="high",
        sandbox="full-access",
        approval="auto",
        autocompact=50,
        timeout=30.0,
        budget=5.0,
        max_turns=10,
    )
    config = MeridianConfig(primary=primary)
    result = RuntimeOverrides.from_config(config)
    for field_name in RuntimeOverrides.model_fields:
        assert getattr(result, field_name) is not None, (
            f"from_config() did not populate '{field_name}'"
        )


def test_resolve_precedence() -> None:
    """resolve() picks first-non-none from ordered layers."""
    from meridian.lib.core.overrides import RuntimeOverrides, resolve

    cli = RuntimeOverrides(model="cli-model")
    env = RuntimeOverrides(model="env-model", thinking="high")
    profile = RuntimeOverrides(model="profile-model", thinking="low", sandbox="full-access")
    config = RuntimeOverrides(
        model="config-model", thinking="medium", sandbox="read-only", budget=10.0
    )

    result = resolve(cli, env, profile, config)
    assert result.model == "cli-model"
    assert result.thinking == "high"
    assert result.sandbox == "full-access"
    assert result.budget == 10.0
