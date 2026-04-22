from pathlib import Path

import pytest

from meridian.lib.config.settings import MeridianConfig
from meridian.lib.core.overrides import RuntimeOverrides
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.launch.context import build_launch_context
from meridian.lib.launch.plan import (
    build_primary_launch_runtime,
    build_primary_spawn_request,
)
from meridian.lib.launch.request import LaunchArgvIntent, LaunchRuntime, SpawnRequest
from meridian.lib.launch.resolve import resolve_policies
from meridian.lib.launch.types import LaunchRequest
from meridian.lib.ops.runtime import build_runtime_from_root_and_config
from meridian.lib.ops.spawn.models import SpawnCreateInput
from meridian.lib.ops.spawn.prepare import build_create_payload
from tests.support.fixtures import write_agent


def _write_minimal_mars_config(project_root: Path) -> None:
    (project_root / "mars.toml").write_text(
        "[settings]\n"
        'targets = [".agents"]\n',
        encoding="utf-8",
    )


def test_resolve_policies_warns_and_uses_no_profile_when_config_agent_is_missing(
    tmp_path: Path,
) -> None:
    _write_minimal_mars_config(tmp_path)

    policies = resolve_policies(
        project_root=tmp_path,
        layers=(),
        config_overrides=RuntimeOverrides(agent="missing-config-agent"),
        config=MeridianConfig(),
        harness_registry=get_default_harness_registry(),
        configured_default_harness="codex",
    )

    assert policies.profile is None
    assert policies.warning is not None
    assert "missing-config-agent" in policies.warning


def test_primary_launch_context_has_no_profile_when_agent_is_unset(tmp_path: Path) -> None:
    _write_minimal_mars_config(tmp_path)
    registry = get_default_harness_registry()

    preview = build_launch_context(
        spawn_id="dry-run-primary",
        request=build_primary_spawn_request(request=LaunchRequest()),
        runtime=build_primary_launch_runtime(project_root=tmp_path),
        harness_registry=registry,
        dry_run=True,
    )

    assert (preview.resolved_request.agent or "") == ""
    assert (preview.resolved_request.agent_metadata.get("session_agent_path") or "") == ""


def test_build_launch_context_surfaces_warning_channel_without_agent_metadata_sidechannel(
    tmp_path: Path,
) -> None:
    _write_minimal_mars_config(tmp_path)
    registry = get_default_harness_registry()

    preview = build_launch_context(
        spawn_id="dry-run-warning",
        request=SpawnRequest(
            prompt="warn",
            model="gpt-5.4",
            harness="codex",
            warning="normalized model alias",
        ),
        runtime=LaunchRuntime(
            argv_intent=LaunchArgvIntent.REQUIRED,
            runtime_root=(tmp_path / ".meridian").as_posix(),
            project_paths_project_root=tmp_path.as_posix(),
            project_paths_execution_cwd=tmp_path.as_posix(),
        ),
        harness_registry=registry,
        dry_run=True,
    )

    assert preview.resolved_request.warning == "normalized model alias"
    assert [warning.message for warning in preview.warnings] == ["normalized model alias"]
    assert "warning" not in preview.resolved_request.agent_metadata


def test_spawn_prepare_derives_harness_from_model_before_default_harness(tmp_path: Path) -> None:
    _write_minimal_mars_config(tmp_path)
    config = MeridianConfig(default_model="claude-sonnet-4", default_harness="codex")
    runtime = build_runtime_from_root_and_config(tmp_path, config)

    prepared = build_create_payload(
        SpawnCreateInput(
            prompt="derive harness from model",
            project_root=tmp_path.as_posix(),
            dry_run=True,
        ),
        runtime=runtime,
    )

    assert prepared.model == "claude-sonnet-4"
    assert prepared.harness == "claude"


def test_resolve_policies_cli_model_override_can_replace_profile_harness(tmp_path: Path) -> None:
    _write_minimal_mars_config(tmp_path)
    write_agent(tmp_path, name="explorer", model="gpt-5.4", harness="codex")

    policies = resolve_policies(
        project_root=tmp_path,
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
            project_root=tmp_path,
            layers=(
                RuntimeOverrides(model="claude-haiku-4-5", harness="codex"),
                RuntimeOverrides(),
            ),
            config_overrides=RuntimeOverrides(),
            config=MeridianConfig(),
            harness_registry=get_default_harness_registry(),
            configured_default_harness="codex",
        )
