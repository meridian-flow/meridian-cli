"""Structural convention tests: RuntimeOverrides field coverage across all config layers."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager


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


_TEST_VALUES: dict[str, str] = {
    "model": "test-model",
    "harness": "claude",
    "agent": "coder",
    "effort": "high",
    "sandbox": "full-access",
    "approval": "auto",
    "autocompact": "50",
    "timeout": "30.0",
}


def test_runtime_overrides_fields_are_exposed_across_env_config_and_cli_layers() -> None:
    from meridian.lib.config.settings import MeridianConfig, PrimaryConfig
    from meridian.lib.core.overrides import RuntimeOverrides
    from meridian.lib.launch.types import LaunchRequest
    from meridian.lib.ops.spawn.models import SpawnCreateInput

    runtime_fields = set(RuntimeOverrides.model_fields.keys())
    config_fields = set(PrimaryConfig.model_fields.keys())
    launch_fields = set(LaunchRequest.model_fields.keys())
    spawn_fields = set(SpawnCreateInput.model_fields.keys())

    for field_name in runtime_fields:
        assert field_name in config_fields
        assert field_name in launch_fields
        assert field_name in spawn_fields

    env_values = {f"MERIDIAN_{k.upper()}": v for k, v in _TEST_VALUES.items()}
    with _env_overrides(env_values):
        from_env = RuntimeOverrides.from_env()

    for field_name in runtime_fields:
        assert getattr(from_env, field_name) is not None

    primary = PrimaryConfig(
        model="test-model",
        harness="claude",
        agent="coder",
        effort="high",
        sandbox="full-access",
        approval="auto",
        autocompact=50,
        timeout=30.0,
    )
    from_config = RuntimeOverrides.from_config(MeridianConfig(primary=primary))
    for field_name in runtime_fields:
        assert getattr(from_config, field_name) is not None


def test_resolve_precedence() -> None:
    from meridian.lib.core.overrides import RuntimeOverrides, resolve

    cli = RuntimeOverrides(model="cli-model")
    env = RuntimeOverrides(model="env-model", effort="high")
    profile = RuntimeOverrides(model="profile-model", effort="low", sandbox="full-access")
    config = RuntimeOverrides(
        model="config-model", effort="medium", sandbox="read-only", timeout=10.0
    )

    result = resolve(cli, env, profile, config)
    assert result.model == "cli-model"
    assert result.effort == "high"
    assert result.sandbox == "full-access"
    assert result.timeout == 10.0


def test_spawn_config_layer_does_not_set_harness() -> None:
    from meridian.lib.config.settings import MeridianConfig
    from meridian.lib.core.overrides import RuntimeOverrides

    overrides = RuntimeOverrides.from_spawn_config(
        MeridianConfig(
            default_model="gpt-5.4",
            default_harness="codex",
        )
    )

    assert overrides.model == "gpt-5.4"
    assert overrides.agent is None
    assert overrides.harness is None
