"""Slice 4b adapter env-override and OpenCode permission injection tests."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

import meridian.lib.safety.permissions as permissions_module
from meridian.lib.domain import Spawn, TokenUsage
from meridian.lib.exec.spawn import execute_with_finalization
from meridian.lib.harness.adapter import (
    ArtifactStore as HarnessArtifactStore,
)
from meridian.lib.harness.adapter import (
    HarnessCapabilities,
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
    TieredPermissionResolver,
    opencode_permission_json,
    validate_permission_config_for_harness,
)
from meridian.lib.space.space_file import create_space
from meridian.lib.state.artifact_store import LocalStore, make_artifact_key
from meridian.lib.state.paths import resolve_space_dir
from meridian.lib.types import HarnessId, ModelId, SpawnId, SpaceId


class _EnvOverrideHarness:
    """Harness that exposes resolved env vars through one stdout JSON line."""

    def __init__(self, *, script: Path) -> None:
        self._script = script
        self.seen_configs: list[PermissionConfig] = []

    @property
    def id(self) -> HarnessId:
        return HarnessId("env-override-test")

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities()

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        _ = run
        return [sys.executable, str(self._script), *perms.resolve_flags(self.id)]

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        self.seen_configs.append(config)
        return {"MERIDIAN_ADAPTER_TIER": config.tier.value}

    def parse_stream_event(self, line: str) -> StreamEvent | None:
        _ = line
        return None

    def extract_usage(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        _ = (artifacts, spawn_id)
        return TokenUsage()

    def extract_session_id(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> str | None:
        _ = (artifacts, spawn_id)
        return None


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
        (PermissionTier.DANGER, {"*": "allow"}),
    ),
)
def test_opencode_permission_json_matches_expected_mappings(
    tier: PermissionTier,
    expected: dict[str, str],
) -> None:
    assert json.loads(opencode_permission_json(tier)) == expected


def test_opencode_permission_json_warns_when_danger_equals_full_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings: list[dict[str, object]] = []

    def _warning(message: str, **kwargs: object) -> None:
        warnings.append({"message": message, "kwargs": kwargs})

    monkeypatch.setattr(permissions_module.logger, "warning", _warning)

    payload = json.loads(opencode_permission_json(PermissionTier.DANGER))
    assert payload == {"*": "allow"}
    assert warnings == [
        {
            "message": "OpenCode has no danger-bypass flag; DANGER falls back to FULL_ACCESS.",
            "kwargs": {"tier": "danger"},
        }
    ]


def test_validate_permission_config_for_harness_warns_on_opencode_danger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings: list[dict[str, object]] = []

    def _warning(message: str, **kwargs: object) -> None:
        warnings.append({"message": message, "kwargs": kwargs})

    monkeypatch.setattr(permissions_module.logger, "warning", _warning)

    config = PermissionConfig(tier=PermissionTier.DANGER, unsafe=True)
    warning = validate_permission_config_for_harness(
        harness_id=HarnessId("opencode"),
        config=config,
    )

    assert warning == "OpenCode has no danger-bypass flag; DANGER falls back to FULL_ACCESS."
    assert warnings == [
        {
            "message": "OpenCode has no danger-bypass flag; DANGER falls back to FULL_ACCESS.",
            "kwargs": {
                "harness_id": "opencode",
                "requested_tier": "danger",
                "effective_tier": "full-access",
            },
        }
    ]


def test_standard_harnesses_only_opencode_sets_env_overrides() -> None:
    config = PermissionConfig(tier=PermissionTier.WORKSPACE_WRITE, unsafe=False)

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


def test_opencode_mcp_config_uses_profile_scoped_tool_globs() -> None:
    mcp_config = OpenCodeAdapter().mcp_config(
        SpawnParams(
            prompt="test",
            model=ModelId("opencode-gpt-5.3-codex"),
            repo_root="/tmp/repo",
            mcp_tools=("spawn_list", "spawn_show"),
        )
    )

    assert mcp_config is not None
    payload = json.loads(mcp_config.env_overrides["OPENCODE_MCP_CONFIG"])
    assert payload["mcp_servers"]["meridian"]["command"] == [
        "uv",
        "run",
        "--directory",
        "/tmp/repo",
        "meridian",
        "serve",
    ]
    assert payload["mcp_servers"]["meridian"]["tool_globs"] == [
        "mcp__meridian__spawn_list",
        "mcp__meridian__spawn_show",
    ]


@pytest.mark.asyncio
async def test_execute_with_finalization_merges_adapter_env_overrides(
    tmp_path: Path,
) -> None:
    script = tmp_path / "print-env.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import os

            print(
                json.dumps(
                    {
                        "caller": os.getenv("MERIDIAN_CALLER_VAR"),
                        "adapter": os.getenv("MERIDIAN_ADAPTER_TIER"),
                        "repo_root": os.getenv("MERIDIAN_REPO_ROOT"),
                        "state_root": os.getenv("MERIDIAN_STATE_ROOT"),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            """
        ),
        encoding="utf-8",
    )

    space = create_space(tmp_path, name="env-overrides")
    run = Spawn(
        spawn_id=SpawnId("r1"),
        prompt="env",
        model=ModelId("gpt-5.3-codex"),
        status="queued",
        space_id=SpaceId(space.id),
    )
    space_dir = resolve_space_dir(tmp_path, space.id)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    adapter = _EnvOverrideHarness(script=script)
    registry = HarnessRegistry()
    registry.register(adapter)

    permission_config = PermissionConfig(
        tier=PermissionTier.WORKSPACE_WRITE,
        unsafe=False,
    )
    exit_code = await execute_with_finalization(
        run,
        repo_root=tmp_path,
        space_dir=space_dir,
        artifacts=artifacts,
        registry=registry,
        permission_resolver=TieredPermissionResolver(permission_config),
        permission_config=permission_config,
        harness_id=adapter.id,
        cwd=tmp_path,
        env_overrides={"MERIDIAN_CALLER_VAR": "caller-value"},
    )

    assert exit_code == 0
    assert adapter.seen_configs == [permission_config]

    output = artifacts.get(make_artifact_key(run.spawn_id, "output.jsonl")).decode("utf-8")
    payload = json.loads(output.strip())
    assert payload == {
        "caller": "caller-value",
        "adapter": PermissionTier.WORKSPACE_WRITE.value,
        "repo_root": tmp_path.as_posix(),
        "state_root": (tmp_path / ".meridian").as_posix(),
    }
