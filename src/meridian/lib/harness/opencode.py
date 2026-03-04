"""OpenCode CLI harness adapter."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import ClassVar

from meridian.lib.harness._common import (
    categorize_stream_event,
    extract_session_id_from_artifacts_with_patterns,
    extract_usage_from_artifacts,
    parse_json_stream_event,
)
from meridian.lib.harness._strategies import (
    FlagEffect,
    FlagStrategy,
    PromptMode,
    StrategyMap,
    build_harness_command,
)
from meridian.lib.harness.adapter import (
    ArtifactStore,
    BaseHarnessAdapter,
    HarnessCapabilities,
    McpConfig,
    PermissionResolver,
    SpawnParams,
    StreamEvent,
)
from meridian.lib.safety.permissions import PermissionConfig, opencode_permission_json
from meridian.lib.types import HarnessId, SpawnId


def _strip_opencode_prefix(model: str) -> str:
    return model[len("opencode-") :] if model.startswith("opencode-") else model


def _opencode_model_transform(value: object, args: list[str]) -> None:
    args.extend(["--model", _strip_opencode_prefix(str(value))])


def _opencode_mcp_globs(run: SpawnParams) -> tuple[str, ...]:
    if run.mcp_tools:
        return tuple(f"mcp__meridian__{tool}" for tool in run.mcp_tools)
    return ("mcp__meridian__*",)


class OpenCodeAdapter(BaseHarnessAdapter):
    """HarnessAdapter implementation for `opencode`."""

    STRATEGIES: ClassVar[StrategyMap] = {
        "model": FlagStrategy(effect=FlagEffect.TRANSFORM, transform=_opencode_model_transform),
        "agent": FlagStrategy(effect=FlagEffect.DROP),
        "skills": FlagStrategy(effect=FlagEffect.DROP),
        "continue_harness_session_id": FlagStrategy(effect=FlagEffect.DROP),
        "continue_fork": FlagStrategy(effect=FlagEffect.DROP),
        "appended_system_prompt": FlagStrategy(effect=FlagEffect.DROP),
    }
    PROMPT_MODE: ClassVar[PromptMode] = PromptMode.POSITIONAL
    BASE_COMMAND: ClassVar[tuple[str, ...]] = ("opencode", "run")
    PRIMARY_BASE_COMMAND: ClassVar[tuple[str, ...]] = ("opencode",)
    EVENT_CATEGORY_MAP: ClassVar[dict[str, str]] = {
        "spawn.start": "sub-run",
        "spawn.done": "sub-run",
        "tool.call": "tool-use",
        "assistant": "assistant",
        "thinking": "thinking",
        "error": "error",
    }
    SESSION_ID_KEYS: ClassVar[tuple[str, ...]] = (
        "session_id",
        "sessionId",
        "sessionID",
    )
    SESSION_ID_TEXT_PATTERNS: ClassVar[tuple[re.Pattern[str], ...]] = (
        re.compile(
            r"\bopencode\b[^\n]*?--session(?:=|\s+)([A-Za-z0-9][A-Za-z0-9._:-]{5,})\b",
            re.IGNORECASE,
        ),
    )

    @property
    def id(self) -> HarnessId:
        return HarnessId("opencode")

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities(
            supports_stream_events=True,
            supports_stdin_prompt=True,
            supports_session_resume=True,
            supports_session_fork=True,
            supports_native_skills=True,
            supports_programmatic_tools=False,
            supports_primary_launch=True,
        )

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        mcp_config = self.mcp_config(run)
        base_command = self.PRIMARY_BASE_COMMAND if run.interactive else self.BASE_COMMAND
        command_run = run if run.interactive else replace(run, prompt="-")
        command = build_harness_command(
            base_command=base_command,
            prompt_mode=self.PROMPT_MODE,
            run=command_run,
            strategies=self.STRATEGIES,
            perms=perms,
            harness_id=self.id,
            mcp_config=mcp_config,
        )
        harness_session_id = (run.continue_harness_session_id or "").strip()
        if not harness_session_id:
            return command
        command.extend(["--session", harness_session_id])
        if run.continue_fork:
            command.append("--fork")
        return command

    def mcp_config(self, run: SpawnParams) -> McpConfig | None:
        repo_root = (run.repo_root or "").strip()
        if not repo_root:
            return None
        payload = {
            "mcp_servers": {
                "meridian": {
                    "command": ["uv", "run", "--directory", repo_root, "meridian", "serve"],
                    "tool_globs": list(_opencode_mcp_globs(run)),
                }
            }
        }
        # MCP sidecar crash behavior:
        # OpenCode reports transport/config errors and the run fails unless the
        # harness itself retries internally. Meridian does not restart sidecars.
        return McpConfig(
            env_overrides={
                "OPENCODE_MCP_CONFIG": json.dumps(payload, sort_keys=True, separators=(",", ":"))
            }
        )

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        return {"OPENCODE_PERMISSION": opencode_permission_json(config.tier)}

    def parse_stream_event(self, line: str) -> StreamEvent | None:
        event = parse_json_stream_event(line)
        if event is None:
            return None
        return categorize_stream_event(event, exact_map=self.EVENT_CATEGORY_MAP)

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId):
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_session_id_from_artifacts_with_patterns(
            artifacts,
            spawn_id,
            json_keys=self.SESSION_ID_KEYS,
            text_patterns=self.SESSION_ID_TEXT_PATTERNS,
        )

