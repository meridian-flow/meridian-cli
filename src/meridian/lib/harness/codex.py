"""Codex CLI harness adapter."""

from __future__ import annotations

import json
from typing import ClassVar

from meridian.lib.harness._common import (
    categorize_stream_event,
    extract_session_id_from_artifacts,
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
    HarnessCapabilities,
    McpConfig,
    PermissionResolver,
    SpawnParams,
    StreamEvent,
)
from meridian.lib.safety.permissions import PermissionConfig
from meridian.lib.types import HarnessId, SpawnId


class CodexAdapter:
    """HarnessAdapter implementation for `codex`."""

    STRATEGIES: ClassVar[StrategyMap] = {
        "model": FlagStrategy(effect=FlagEffect.CLI_FLAG, cli_flag="--model"),
        "agent": FlagStrategy(effect=FlagEffect.DROP),
        "skills": FlagStrategy(effect=FlagEffect.DROP),
        "continue_harness_session_id": FlagStrategy(effect=FlagEffect.DROP),
        "continue_fork": FlagStrategy(effect=FlagEffect.DROP),
        "appended_system_prompt": FlagStrategy(effect=FlagEffect.DROP),
    }
    PROMPT_MODE: ClassVar[PromptMode] = PromptMode.POSITIONAL
    BASE_COMMAND: ClassVar[tuple[str, ...]] = ("codex", "exec")
    EVENT_CATEGORY_MAP: ClassVar[dict[str, str]] = {
        "response.completed": "lifecycle",
        "response.output_text.delta": "assistant",
        "response.reasoning_summary.delta": "thinking",
        "tool.call.started": "tool-use",
        "tool.call.completed": "tool-use",
        "error": "error",
    }

    @property
    def id(self) -> HarnessId:
        return HarnessId("codex")

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities(
            supports_stream_events=True,
            supports_session_resume=True,
            supports_native_skills=True,
            supports_programmatic_tools=False,
        )

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        mcp_config = self.mcp_config(run)
        harness_session_id = (run.continue_harness_session_id or "").strip()
        base_command = (
            ("codex", "exec", "resume", harness_session_id)
            if harness_session_id
            else self.BASE_COMMAND
        )
        return build_harness_command(
            base_command=base_command,
            prompt_mode=self.PROMPT_MODE,
            run=run,
            strategies=self.STRATEGIES,
            perms=perms,
            harness_id=self.id,
            mcp_config=mcp_config,
        )

    def mcp_config(self, run: SpawnParams) -> McpConfig | None:
        repo_root = (run.repo_root or "").strip()
        if not repo_root:
            return None
        # Codex expects command as a string and args as a separate array,
        # not command as an array like Claude's MCP config.
        args_literal = json.dumps(
            ["run", "--directory", repo_root, "meridian", "serve"],
            separators=(",", ":"),
        )
        config_args = [
            "--config",
            'mcp_servers.meridian.command="uv"',
            "--config",
            f"mcp_servers.meridian.args={args_literal}",
        ]

        if run.mcp_tools:
            enabled_tools_literal = json.dumps(list(run.mcp_tools), separators=(",", ":"))
            config_args.extend(
                [
                    "--config",
                    f"mcp_servers.meridian.enabled_tools={enabled_tools_literal}",
                ]
            )

        # MCP sidecar crash behavior:
        # Codex reports a tool transport failure and exits non-zero; Meridian does not
        # auto-reconnect sidecars and relies on normal run retry policy.
        return McpConfig(command_args=tuple(config_args))

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        _ = config
        return {}

    def parse_stream_event(self, line: str) -> StreamEvent | None:
        event = parse_json_stream_event(line)
        if event is None:
            return None
        return categorize_stream_event(event, exact_map=self.EVENT_CATEGORY_MAP)

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId):
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_session_id_from_artifacts(artifacts, spawn_id)

    def extract_tasks(self, event: StreamEvent) -> list[dict[str, str]] | None:
        _ = event
        return None

    def extract_findings(self, event: StreamEvent) -> list[dict[str, str]] | None:
        _ = event
        return None

    def extract_summary(self, output: str) -> str | None:
        _ = output
        return None
