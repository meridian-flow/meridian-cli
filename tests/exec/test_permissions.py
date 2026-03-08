
import json
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from meridian.lib.core.domain import Spawn, TokenUsage
from meridian.lib.launch.command import build_launch_env
from meridian.lib.launch.env import build_harness_child_env
from meridian.lib.launch.env import inherit_child_env
from meridian.lib.launch.env import sanitize_child_env
from meridian.lib.launch.types import LaunchRequest
from meridian.lib.launch.runner import execute_with_finalization
from meridian.lib.harness.common import (
    extract_session_id_from_artifacts,
    extract_usage_from_artifacts,
)
from meridian.lib.harness.adapter import (
    ArtifactStore as HarnessArtifactStore,
    BaseHarnessAdapter,
    HarnessCapabilities,
    McpConfig,
    PermissionResolver,
    SpawnParams,
    StreamEvent,
)
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.safety.permissions import (
    PermissionConfig,
    PermissionTier,
    build_permission_config,
    opencode_permission_json,
    permission_flags_for_harness,
)
from meridian.lib.state.artifact_store import LocalStore, make_artifact_key
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.core.types import HarnessId, ModelId, SpawnId


class ScriptHarnessAdapter(BaseHarnessAdapter):
    def __init__(self, *, command: tuple[str, ...]) -> None:
        self._command = command

    @property
    def id(self) -> HarnessId:
        return HarnessId("exec-permissions")

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities()

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        return [*self._command, *perms.resolve_flags(self.id), *run.extra_args]

    def mcp_config(self, run: SpawnParams) -> McpConfig | None:
        _ = run
        return None

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        _ = config
        return {}

    def parse_stream_event(self, line: str) -> StreamEvent | None:
        _ = line
        return None

    def extract_usage(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def extract_session_id(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_session_id_from_artifacts(artifacts, spawn_id)


def _create_run(repo_root: Path, *, prompt: str, spawn_id: str = "r1") -> tuple[Spawn, Path]:
    run = Spawn(
        spawn_id=SpawnId(spawn_id),
        prompt=prompt,
        model=ModelId("gpt-5.3-codex"),
        status="queued",
    )
    return run, resolve_state_paths(repo_root).root_dir


def _write_script(path: Path, source: str, *, executable: bool = False) -> None:
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    if executable:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR)


def test_auto_approval_bypass_and_invalid_approval() -> None:
    config = build_permission_config("full-access", approval="auto")
    assert config.tier is PermissionTier.FULL_ACCESS
    assert config.approval == "auto"
    assert permission_flags_for_harness(HarnessId("claude"), config) == [
        "--dangerously-skip-permissions"
    ]
    assert permission_flags_for_harness(HarnessId("codex"), config) == [
        "--dangerously-bypass-approvals-and-sandbox"
    ]

    with pytest.raises(ValueError, match="Unsupported approval mode"):
        build_permission_config("full-access", approval="sometimes")


@pytest.mark.parametrize(
    ("tier", "expected"),
    (
        (
            PermissionTier.READ_ONLY,
            {"*": "deny", "read": "allow", "grep": "allow", "glob": "allow", "list": "allow"},
        ),
        (
            PermissionTier.WORKSPACE_WRITE,
            {
                "*": "deny",
                "read": "allow",
                "grep": "allow",
                "glob": "allow",
                "list": "allow",
                "edit": "allow",
                "bash": "deny",
            },
        ),
        (PermissionTier.FULL_ACCESS, {"*": "allow"}),
    ),
)
def test_opencode_permission_json_matches_expected_mappings(
    tier: PermissionTier,
    expected: dict[str, str],
) -> None:
    assert json.loads(opencode_permission_json(tier)) == expected


def test_standard_harnesses_only_opencode_sets_env_overrides() -> None:
    config = PermissionConfig(tier=PermissionTier.WORKSPACE_WRITE, approval="confirm")

    assert ClaudeAdapter().env_overrides(config) == {}
    assert CodexAdapter().env_overrides(config) == {}
    assert json.loads(OpenCodeAdapter().env_overrides(config)["OPENCODE_PERMISSION"]) == {
        "*": "deny",
        "read": "allow",
        "grep": "allow",
        "glob": "allow",
        "list": "allow",
        "edit": "allow",
        "bash": "deny",
    }


def test_sanitize_child_env_filters_parent_secrets_and_keeps_explicit_overrides() -> None:
    base_env = {
        "PATH": "/usr/bin",
        "HOME": "/home/tester",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "C.UTF-8",
        "XDG_RUNTIME_DIR": "/tmp/xdg",
        "UV_CACHE_DIR": "/tmp/uv",
        "EXAMPLE_TOKEN": "drop-me",
        "EXAMPLE_KEY": "drop-me-too",
        "ANTHROPIC_API_KEY": "allowed-credential",
    }
    env_overrides = {
        "MERIDIAN_DEPTH": "2",
        "CUSTOM_SECRET": "explicit-override",
    }

    sanitized = sanitize_child_env(
        base_env=base_env,
        env_overrides=env_overrides,
        pass_through={"ANTHROPIC_API_KEY"},
    )

    assert sanitized["PATH"] == "/usr/bin"
    assert sanitized["HOME"] == "/home/tester"
    assert sanitized["LC_ALL"] == "C.UTF-8"
    assert sanitized["XDG_RUNTIME_DIR"] == "/tmp/xdg"
    assert sanitized["UV_CACHE_DIR"] == "/tmp/uv"
    assert sanitized["ANTHROPIC_API_KEY"] == "allowed-credential"
    assert sanitized["MERIDIAN_DEPTH"] == "2"
    assert sanitized["CUSTOM_SECRET"] == "explicit-override"
    assert "EXAMPLE_TOKEN" not in sanitized
    assert "EXAMPLE_KEY" not in sanitized


def test_sanitize_child_env_does_not_leak_primary_autocompact_override() -> None:
    sanitized = sanitize_child_env(
        base_env={
            "PATH": "/usr/bin",
            "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "67",
        },
        env_overrides={"MERIDIAN_DEPTH": "2"},
        pass_through=set(),
    )

    assert sanitized["PATH"] == "/usr/bin"
    assert sanitized["MERIDIAN_DEPTH"] == "2"
    assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" not in sanitized


def test_sanitize_child_env_derives_fs_from_repo_root() -> None:
    sanitized = sanitize_child_env(
        base_env={"PATH": "/usr/bin"},
        env_overrides={
            "MERIDIAN_REPO_ROOT": "/tmp/repo",
        },
        pass_through=set(),
    )

    assert sanitized["MERIDIAN_REPO_ROOT"] == "/tmp/repo"
    assert sanitized["MERIDIAN_FS_DIR"] == "/tmp/repo/.meridian/fs"


def test_build_launch_env_propagates_explicit_primary_chat_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.delenv("MERIDIAN_CHAT_ID", raising=False)

    child_env = build_launch_env(
        tmp_path,
        LaunchRequest(),
        chat_id="c42",
    )

    assert child_env["MERIDIAN_CHAT_ID"] == "c42"
    assert child_env["MERIDIAN_FS_DIR"] == (tmp_path / ".meridian" / "fs").as_posix()


def test_sanitize_child_env_prefers_state_root_for_fs() -> None:
    sanitized = sanitize_child_env(
        base_env={"PATH": "/usr/bin"},
        env_overrides={
            "MERIDIAN_REPO_ROOT": "/tmp/repo",
            "MERIDIAN_STATE_ROOT": "/tmp/custom-state",
        },
        pass_through=set(),
    )

    assert sanitized["MERIDIAN_FS_DIR"] == "/tmp/custom-state/fs"


def test_inherit_child_env_keeps_parent_env_but_drops_internal_launch_overrides() -> None:
    inherited = inherit_child_env(
        base_env={
            "PATH": "/usr/bin",
            "UNRELATED_TOKEN": "keep-me",
            "MISC_VALUE": "keep-too",
            "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "67",
            "MERIDIAN_PRIMARY_PROMPT": "stale",
        },
        env_overrides={"MERIDIAN_DEPTH": "2"},
    )

    assert inherited["PATH"] == "/usr/bin"
    assert inherited["UNRELATED_TOKEN"] == "keep-me"
    assert inherited["MISC_VALUE"] == "keep-too"
    assert inherited["MERIDIAN_DEPTH"] == "2"
    assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" not in inherited
    assert "MERIDIAN_PRIMARY_PROMPT" not in inherited


def test_build_harness_child_env_uses_claude_specific_blocklist() -> None:
    child_env = build_harness_child_env(
        base_env={
            "PATH": "/usr/bin",
            "CLAUDECODE": "1",
            "UNRELATED_TOKEN": "keep-me",
            "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "67",
        },
        adapter=ClaudeAdapter(),
        run_params=SpawnParams(prompt="test", model=ModelId("claude-sonnet-4-6")),
        permission_config=PermissionConfig(),
        runtime_env_overrides={"MERIDIAN_DEPTH": "2"},
    )

    assert child_env["PATH"] == "/usr/bin"
    assert child_env["UNRELATED_TOKEN"] == "keep-me"
    assert child_env["MERIDIAN_DEPTH"] == "2"
    assert "CLAUDECODE" not in child_env
    assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" not in child_env


def test_build_harness_child_env_does_not_block_claudecode_for_other_harnesses() -> None:
    child_env = build_harness_child_env(
        base_env={
            "PATH": "/usr/bin",
            "CLAUDECODE": "1",
        },
        adapter=CodexAdapter(),
        run_params=SpawnParams(prompt="test", model=ModelId("gpt-5.3-codex")),
        permission_config=PermissionConfig(),
        runtime_env_overrides={"MERIDIAN_DEPTH": "2"},
    )

    assert child_env["PATH"] == "/usr/bin"
    assert child_env["CLAUDECODE"] == "1"
    assert child_env["MERIDIAN_DEPTH"] == "2"
