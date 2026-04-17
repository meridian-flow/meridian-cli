import json
from pathlib import Path

import pytest

from meridian.lib.config.settings import MeridianConfig
from meridian.lib.core.overrides import RuntimeOverrides
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.harness.workspace_projection import OPENCODE_CONFIG_CONTENT_ENV
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


def test_primary_launch_context_has_no_profile_when_agent_is_unset(tmp_path: Path) -> None:
    _write_minimal_mars_config(tmp_path)
    registry = get_default_harness_registry()

    preview = build_launch_context(
        spawn_id="dry-run-primary",
        request=build_primary_spawn_request(request=LaunchRequest()),
        runtime=build_primary_launch_runtime(repo_root=tmp_path),
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
            state_root=(tmp_path / ".meridian").as_posix(),
            project_paths_repo_root=tmp_path.as_posix(),
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
            repo_root=tmp_path.as_posix(),
            dry_run=True,
        ),
        runtime=runtime,
    )

    assert prepared.model == "claude-sonnet-4"
    assert prepared.harness == "claude"


def test_spawn_prepare_fails_when_workspace_file_is_invalid(tmp_path: Path) -> None:
    _write_minimal_mars_config(tmp_path)
    (tmp_path / "workspace.local.toml").write_text("[[context-roots]]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid workspace file"):
        build_create_payload(
            SpawnCreateInput(
                prompt="invalid workspace should fail before launch",
                repo_root=tmp_path.as_posix(),
                dry_run=True,
            )
        )


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
    registry = get_default_harness_registry()

    preview = build_launch_context(
        spawn_id="dry-run-primary",
        request=build_primary_spawn_request(
            request=LaunchRequest(model="claude-sonnet-4", agent="dev-orchestrator")
        ),
        runtime=build_primary_launch_runtime(repo_root=tmp_path),
        harness_registry=registry,
        dry_run=True,
    )

    command_text = " ".join(preview.argv)
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
    registry = get_default_harness_registry()

    preview = build_launch_context(
        spawn_id="dry-run-primary",
        request=build_primary_spawn_request(
            request=LaunchRequest(model="gpt-5.4", agent="dev-orchestrator")
        ),
        runtime=build_primary_launch_runtime(repo_root=tmp_path),
        harness_registry=registry,
        dry_run=True,
    )

    prompt = preview.run_params.prompt
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
    registry = get_default_harness_registry()

    preview = build_launch_context(
        spawn_id="dry-run-primary",
        request=build_primary_spawn_request(
            request=LaunchRequest(
                model="opencode-gpt-5.3-codex",
                agent="dev-orchestrator",
            )
        ),
        runtime=build_primary_launch_runtime(repo_root=tmp_path),
        harness_registry=registry,
        dry_run=True,
    )

    prompt = preview.run_params.prompt
    assert "# Meridian Agents" in prompt
    assert "AGENTS" in prompt
    assert "- dev-orchestrator" in prompt
    assert "- smoke-tester" in prompt
    assert "SKILLS" not in prompt
    assert "verification: Verification helper" not in prompt


def test_workspace_roots_append_after_claude_preflight_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_minimal_mars_config(tmp_path)
    shared_root = tmp_path / "shared"
    shared_root.mkdir()
    (tmp_path / "workspace.local.toml").write_text(
        "[[context-roots]]\n"
        'path = "./shared"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAUDECODE", "1")
    registry = get_default_harness_registry()

    preview = build_launch_context(
        spawn_id="dry-run-claude-workspace-order",
        request=SpawnRequest(
            prompt="workspace order",
            model="claude-sonnet-4-5",
            harness="claude",
            extra_args=("--user-tail", "1"),
        ),
        runtime=LaunchRuntime(
            argv_intent=LaunchArgvIntent.REQUIRED,
            state_root=(tmp_path / ".meridian").as_posix(),
            project_paths_repo_root=tmp_path.as_posix(),
            project_paths_execution_cwd=tmp_path.as_posix(),
        ),
        harness_registry=registry,
        dry_run=True,
    )

    assert preview.run_params.extra_args == (
        "--user-tail",
        "1",
        "--add-dir",
        tmp_path.as_posix(),
        "--add-dir",
        shared_root.as_posix(),
    )


def test_workspace_roots_project_to_opencode_config_content_env(tmp_path: Path) -> None:
    _write_minimal_mars_config(tmp_path)
    shared_root = tmp_path / "shared"
    shared_root.mkdir()
    (tmp_path / "workspace.local.toml").write_text(
        "[[context-roots]]\n"
        'path = "./shared"\n',
        encoding="utf-8",
    )
    registry = get_default_harness_registry()

    preview = build_launch_context(
        spawn_id="dry-run-opencode-workspace",
        request=SpawnRequest(
            prompt="workspace projection",
            model="opencode-gpt-5.3-codex",
            harness="opencode",
        ),
        runtime=LaunchRuntime(
            argv_intent=LaunchArgvIntent.REQUIRED,
            state_root=(tmp_path / ".meridian").as_posix(),
            project_paths_repo_root=tmp_path.as_posix(),
            project_paths_execution_cwd=tmp_path.as_posix(),
        ),
        harness_registry=registry,
        dry_run=True,
    )

    payload = json.loads(preview.env_overrides[OPENCODE_CONFIG_CONTENT_ENV])
    assert payload == {
        "permission": {"external_directory": [shared_root.as_posix()]},
    }


def test_opencode_workspace_projection_reports_parent_env_suppression(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_minimal_mars_config(tmp_path)
    shared_root = tmp_path / "shared"
    shared_root.mkdir()
    (tmp_path / "workspace.local.toml").write_text(
        "[[context-roots]]\n"
        'path = "./shared"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(
        OPENCODE_CONFIG_CONTENT_ENV,
        '{"permission":{"external_directory":["/existing"]}}',
    )
    registry = get_default_harness_registry()

    preview = build_launch_context(
        spawn_id="dry-run-opencode-workspace-suppressed",
        request=SpawnRequest(
            prompt="workspace projection",
            model="opencode-gpt-5.3-codex",
            harness="opencode",
        ),
        runtime=LaunchRuntime(
            argv_intent=LaunchArgvIntent.REQUIRED,
            state_root=(tmp_path / ".meridian").as_posix(),
            project_paths_repo_root=tmp_path.as_posix(),
            project_paths_execution_cwd=tmp_path.as_posix(),
        ),
        harness_registry=registry,
        dry_run=True,
    )

    assert OPENCODE_CONFIG_CONTENT_ENV not in preview.env_overrides
    warning_codes = {warning.code for warning in preview.warnings}
    assert "workspace_opencode_parent_env_suppressed" in warning_codes
