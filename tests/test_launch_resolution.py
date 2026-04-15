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
from tests.helpers.fixtures import write_agent, write_skill


def _write_minimal_mars_config(repo_root: Path) -> None:
    (repo_root / "mars.toml").write_text(
        "[settings]\n"
        'targets = [".agents"]\n',
        encoding="utf-8",
    )


def test_resolve_policies_warns_and_uses_no_profile_when_config_agent_is_missing(
    tmp_path: Path,
) -> None:
    _write_minimal_mars_config(tmp_path)

    policies = resolve_policies(
        repo_root=tmp_path,
        layers=(),
        config_overrides=RuntimeOverrides(agent="missing-config-agent"),
        config=MeridianConfig(),
        harness_registry=get_default_harness_registry(),
        configured_default_harness="codex",
    )

    assert policies.profile is None
    assert policies.warning is not None
    assert "missing-config-agent" in policies.warning


def test_resolve_primary_launch_plan_has_no_profile_when_agent_is_unset(tmp_path: Path) -> None:
    _write_minimal_mars_config(tmp_path)

    plan = resolve_primary_launch_plan(
        repo_root=tmp_path,
        request=LaunchRequest(),
        harness_registry=get_default_harness_registry(),
    )

    assert plan.session_metadata.agent == ""
    assert plan.session_metadata.agent_path == ""


def test_spawn_prepare_derives_harness_from_model_before_default_harness(tmp_path: Path) -> None:
    _write_minimal_mars_config(tmp_path)
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
    _write_minimal_mars_config(tmp_path)
    write_agent(tmp_path, name="explorer", model="gpt-5.4", harness="codex")

    policies = resolve_policies(
        repo_root=tmp_path,
        layers=(
            RuntimeOverrides(agent="explorer", model="claude-haiku-4-5"),
            RuntimeOverrides(),
        ),
        config_overrides=RuntimeOverrides(),
        config=MeridianConfig(),
        harness_registry=get_default_harness_registry(),
        configured_default_harness="codex",
    )

    assert str(policies.harness) == "claude"


def test_resolve_policies_errors_on_same_layer_user_harness_model_conflict(tmp_path: Path) -> None:
    _write_minimal_mars_config(tmp_path)
    with pytest.raises(ValueError, match="incompatible with model"):
        resolve_policies(
            repo_root=tmp_path,
            layers=(
                RuntimeOverrides(model="claude-haiku-4-5", harness="codex"),
                RuntimeOverrides(),
            ),
            config_overrides=RuntimeOverrides(),
            config=MeridianConfig(),
            harness_registry=get_default_harness_registry(),
            configured_default_harness="codex",
        )


def test_primary_launch_injects_inventory_into_claude_system_prompt(tmp_path: Path) -> None:
    _write_minimal_mars_config(tmp_path)
    write_agent(tmp_path, name="dev-orchestrator", model="claude-sonnet-4")
    write_agent(tmp_path, name="coder", model="gpt-5.4")
    write_skill(tmp_path, "meridian-spawn", description="Spawn helper")
    write_skill(tmp_path, "review", description="Review helper")

    plan = resolve_primary_launch_plan(
        repo_root=tmp_path,
        request=LaunchRequest(model="claude-sonnet-4", agent="dev-orchestrator"),
        harness_registry=get_default_harness_registry(),
    )

    command_text = " ".join(plan.command)
    assert "# Meridian Agents" in command_text
    assert "AGENTS" in command_text
    assert "- dev-orchestrator" in command_text
    assert "- coder" in command_text
    assert "SKILLS" not in command_text
    assert "meridian-spawn: Spawn helper" not in command_text
    assert "review: Review helper" not in command_text


def test_primary_launch_injects_inventory_inline_for_codex(tmp_path: Path) -> None:
    _write_minimal_mars_config(tmp_path)
    write_agent(tmp_path, name="dev-orchestrator", model="gpt-5.4")
    write_agent(tmp_path, name="reviewer", model="claude-sonnet-4")
    write_skill(tmp_path, "meridian-spawn", description="Spawn helper")

    plan = resolve_primary_launch_plan(
        repo_root=tmp_path,
        request=LaunchRequest(model="gpt-5.4", agent="dev-orchestrator"),
        harness_registry=get_default_harness_registry(),
    )

    prompt = plan.run_params.prompt
    assert "# Meridian Agents" in prompt
    assert "AGENTS" in prompt
    assert "- dev-orchestrator" in prompt
    assert "- reviewer" in prompt
    assert "SKILLS" not in prompt
    assert "meridian-spawn: Spawn helper" not in prompt


def test_primary_launch_injects_inventory_inline_for_opencode(tmp_path: Path) -> None:
    _write_minimal_mars_config(tmp_path)
    write_agent(tmp_path, name="dev-orchestrator", model="opencode-gpt-5.3-codex")
    write_agent(tmp_path, name="smoke-tester", model="claude-sonnet-4")
    write_skill(tmp_path, "verification", description="Verification helper")

    plan = resolve_primary_launch_plan(
        repo_root=tmp_path,
        request=LaunchRequest(model="opencode-gpt-5.3-codex", agent="dev-orchestrator"),
        harness_registry=get_default_harness_registry(),
    )

    prompt = plan.run_params.prompt
    assert "# Meridian Agents" in prompt
    assert "AGENTS" in prompt
    assert "- dev-orchestrator" in prompt
    assert "- smoke-tester" in prompt
    assert "SKILLS" not in prompt
    assert "verification: Verification helper" not in prompt
