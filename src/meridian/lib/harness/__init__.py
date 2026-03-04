"""Harness adapter abstractions and built-in implementations."""

from meridian.lib.harness.adapter import (
    ArtifactStore,
    BaseHarnessAdapter,
    HarnessAdapter,
    HarnessCapabilities,
    McpConfig,
    PermissionResolver,
    SpawnParams,
    SpawnResult,
    StreamEvent,
    resolve_mcp_config,
)
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.direct import DirectAdapter
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.harness.registry import HarnessRegistry, get_default_harness_registry

__all__ = [
    "ArtifactStore",
    "BaseHarnessAdapter",
    "ClaudeAdapter",
    "CodexAdapter",
    "DirectAdapter",
    "HarnessAdapter",
    "HarnessCapabilities",
    "HarnessRegistry",
    "McpConfig",
    "OpenCodeAdapter",
    "PermissionResolver",
    "SpawnParams",
    "SpawnResult",
    "StreamEvent",
    "get_default_harness_registry",
    "resolve_mcp_config",
]
