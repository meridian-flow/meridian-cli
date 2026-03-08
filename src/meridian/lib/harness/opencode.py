"""OpenCode CLI harness adapter."""


import re
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from meridian.lib.harness.common import (
    categorize_stream_event,
    extract_opencode_report,
    extract_session_id_from_artifacts_with_patterns,
    extract_usage_from_artifacts,
    parse_json_stream_event,
)
from meridian.lib.harness.common import (
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
from meridian.lib.harness.launch_types import PromptPolicy
from meridian.lib.harness.session_detection import resolve_opencode_primary_session_id
from meridian.lib.safety.permissions import PermissionConfig, opencode_permission_json
from meridian.lib.core.types import HarnessId, SpawnId


def _strip_opencode_prefix(model: str) -> str:
    return model[len("opencode-") :] if model.startswith("opencode-") else model


def _opencode_model_transform(value: object, args: list[str]) -> None:
    args.extend(["--model", _strip_opencode_prefix(str(value))])


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
        base_command = self.PRIMARY_BASE_COMMAND if run.interactive else self.BASE_COMMAND
        command_run = run if run.interactive else run.model_copy(update={"prompt": "-"})
        command = build_harness_command(
            base_command=base_command,
            prompt_mode=self.PROMPT_MODE,
            run=command_run,
            strategies=self.STRATEGIES,
            perms=perms,
            harness_id=self.id,
        )
        harness_session_id = (run.continue_harness_session_id or "").strip()
        if not harness_session_id:
            return command
        command.extend(["--session", harness_session_id])
        if run.continue_fork:
            command.append("--fork")
        return command

    def mcp_config(self, run: SpawnParams) -> McpConfig | None:
        # MCP injection is off by default — agents use the CLI instead.
        # Users who want always-on MCP can configure it in their harness settings.
        return None

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        return {"OPENCODE_PERMISSION": opencode_permission_json(config.tier)}

    def parse_stream_event(self, line: str) -> StreamEvent | None:
        event = parse_json_stream_event(line)
        if event is None:
            return None
        return categorize_stream_event(event, exact_map=self.EVENT_CATEGORY_MAP)

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId):
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def filter_launch_content(
        self,
        *,
        prompt: str,
        skill_injection: str | None,
        is_resume: bool,
        harness_session_id: str,
    ) -> PromptPolicy:
        _ = harness_session_id
        if is_resume:
            return PromptPolicy()
        return PromptPolicy(prompt=prompt, skill_injection=skill_injection)

    def detect_primary_session_id(
        self,
        *,
        repo_root: Path,
        started_at_epoch: float,
        started_at_local_iso: str | None,
    ) -> str | None:
        local_iso = (
            started_at_local_iso
            if started_at_local_iso is not None
            else datetime.fromtimestamp(started_at_epoch).strftime("%Y-%m-%dT%H:%M:%S")
        )
        return resolve_opencode_primary_session_id(repo_root, started_at_epoch, local_iso)

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_session_id_from_artifacts_with_patterns(
            artifacts,
            spawn_id,
            json_keys=self.SESSION_ID_KEYS,
            text_patterns=self.SESSION_ID_TEXT_PATTERNS,
        )

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_opencode_report(artifacts, spawn_id)
