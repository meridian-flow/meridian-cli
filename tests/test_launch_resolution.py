from pathlib import Path

import pytest

from meridian.lib.config.settings import MeridianConfig
from meridian.lib.core.overrides import RuntimeOverrides
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.launch.plan import resolve_primary_launch_plan
from meridian.lib.launch.resolve import resolve_policies
from meridian.lib.launch.types import LaunchRequest
from meridian.lib.ops.runtime import build_runtime_from_root_and_config
from meridian.lib.ops.spawn.models import SpawnCreateInput
from meridian.lib.ops.spawn.prepare import build_create_payload
from tests.helpers.fixtures import write_agent


def test_resolve_policies_treats_config_agent_as_configured_default(tmp_path: Path) -> None:
    write_agent(tmp_path, name="__meridian-subagent", model="gpt-5.4")

    policies = resolve_policies(
        repo_root=tmp_path,
        layers=(),
        config_overrides=RuntimeOverrides(agent="missing-config-agent"),
        config=MeridianConfig(),
        harness_registry=get_default_harness_registry(),
        builtin_default_agent="__meridian-subagent",
        configured_default_harness="codex",
    )

    assert policies.profile is not None
    assert policies.profile.name == "__meridian-subagent"
    assert policies.warning is not None
    assert "missing-config-agent" in policies.warning


def test_resolve_primary_launch_plan_uses_defaults_primary_agent(tmp_path: Path) -> None:
    write_agent(tmp_path, name="custom-primary", model="gpt-5.4")
    config = MeridianConfig(primary_agent="custom-primary")

    plan = resolve_primary_launch_plan(
        repo_root=tmp_path,
        request=LaunchRequest(),
        harness_registry=get_default_harness_registry(),
        config=config,
    )

    assert plan.session_metadata.agent == "custom-primary"
    assert plan.session_metadata.agent_path.endswith("/.agents/agents/custom-primary.md")


def test_spawn_prepare_derives_harness_from_model_before_default_harness(tmp_path: Path) -> None:
    config = MeridianConfig(default_model="claude-sonnet-4", default_harness="codex")
    runtime = build_runtime_from_root_and_config(tmp_path, config)

    prepared = build_create_payload(
        SpawnCreateInput(
            prompt="derive harness from model",
            repo_root=tmp_path.as_posix(),
            dry_run=True,
        ),
        runtime=runtime,
    )

    assert prepared.model == "claude-sonnet-4"
    assert prepared.harness_id == "claude"


def test_resolve_policies_cli_model_override_can_replace_profile_harness(tmp_path: Path) -> None:
    write_agent(tmp_path, name="explorer", model="gpt-5.4", harness="codex")

    policies = resolve_policies(
        repo_root=tmp_path,
        layers=(RuntimeOverrides(agent="explorer", model="haiku"), RuntimeOverrides()),
        config_overrides=RuntimeOverrides(),
        config=MeridianConfig(),
        harness_registry=get_default_harness_registry(),
        configured_default_harness="codex",
    )

    assert str(policies.harness) == "claude"


def test_resolve_policies_errors_on_same_layer_user_harness_model_conflict(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="incompatible with model"):
        resolve_policies(
            repo_root=tmp_path,
            layers=(RuntimeOverrides(model="haiku", harness="codex"), RuntimeOverrides()),
            config_overrides=RuntimeOverrides(),
            config=MeridianConfig(),
            harness_registry=get_default_harness_registry(),
            configured_default_harness="codex",
        )
