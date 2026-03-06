"""Slice 4b adapter env-override and OpenCode permission injection tests."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

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
