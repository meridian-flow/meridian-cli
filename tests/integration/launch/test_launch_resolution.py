import json
from pathlib import Path

import pytest

from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.harness.workspace_projection import OPENCODE_CONFIG_CONTENT_ENV
from meridian.lib.launch.context import build_launch_context
from meridian.lib.launch.plan import (
    build_primary_launch_runtime,
    build_primary_spawn_request,
)
from meridian.lib.launch.request import LaunchArgvIntent, LaunchRuntime, SpawnRequest
from meridian.lib.launch.types import LaunchRequest
from tests.support.fixtures import write_agent, write_skill


def _write_minimal_mars_config(repo_root: Path) -> None:
    (repo_root / "mars.toml").write_text(
        "[settings]\n"
        'targets = [".agents"]\n',
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("model", "peer_name", "peer_model", "skill_name", "skill_description", "expect_inline"),
    [
        (
            "claude-sonnet-4",
            "coder",
            "gpt-5.4",
            "review",
            "Review helper",
            False,
        ),
        (
            "gpt-5.4",
            "reviewer",
            "claude-sonnet-4",
            "meridian-spawn",
            "Spawn helper",
            True,
        ),
        (
            "opencode-gpt-5.3-codex",
            "smoke-tester",
            "claude-sonnet-4",
            "verification",
            "Verification helper",
            True,
        ),
    ],
    ids=["claude", "codex", "opencode"],
)
def test_primary_launch_injects_inventory_by_harness_family(
    tmp_path: Path,
    model: str,
    peer_name: str,
    peer_model: str,
    skill_name: str,
    skill_description: str,
    expect_inline: bool,
) -> None:
    _write_minimal_mars_config(tmp_path)
    write_agent(tmp_path, name="dev-orchestrator", model=model)
    write_agent(tmp_path, name=peer_name, model=peer_model)
    write_skill(tmp_path, skill_name, description=skill_description)
    registry = get_default_harness_registry()

    preview = build_launch_context(
        spawn_id="dry-run-primary",
        request=build_primary_spawn_request(
            request=LaunchRequest(model=model, agent="dev-orchestrator")
        ),
        runtime=build_primary_launch_runtime(repo_root=tmp_path),
        harness_registry=registry,
        dry_run=True,
    )

    text = preview.run_params.prompt if expect_inline else " ".join(preview.argv)
    assert "# Meridian Agents" in text
    assert "AGENTS" in text
    assert "- dev-orchestrator" in text
    assert f"- {peer_name}" in text
    assert "SKILLS" not in text
    assert f"{skill_name}: {skill_description}" not in text


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

    state_root = tmp_path / ".meridian"
    assert preview.run_params.extra_args == (
        "--user-tail",
        "1",
        "--add-dir",
        tmp_path.as_posix(),
        "--add-dir",
        shared_root.as_posix(),
        "--add-dir",
        state_root.as_posix(),
    )


@pytest.mark.parametrize(
    "parent_env_present",
    [False, True],
    ids=["without_parent_env", "with_parent_env"],
)
def test_opencode_workspace_projection_handles_parent_env_suppression(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    parent_env_present: bool,
) -> None:
    _write_minimal_mars_config(tmp_path)
    shared_root = tmp_path / "shared"
    shared_root.mkdir()
    (tmp_path / "workspace.local.toml").write_text(
        "[[context-roots]]\n"
        'path = "./shared"\n',
        encoding="utf-8",
    )
    if parent_env_present:
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

    warning_codes = {warning.code for warning in preview.warnings}
    if parent_env_present:
        assert OPENCODE_CONFIG_CONTENT_ENV not in preview.env_overrides
        assert "workspace_opencode_parent_env_suppressed" in warning_codes
    else:
        state_root = tmp_path / ".meridian"
        payload = json.loads(preview.env_overrides[OPENCODE_CONFIG_CONTENT_ENV])
        assert payload == {
            "permission": {"external_directory": [shared_root.as_posix(), state_root.as_posix()]},
        }
        assert "workspace_opencode_parent_env_suppressed" not in warning_codes
