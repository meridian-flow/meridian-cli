"""Codex CLI harness adapter."""


from pathlib import Path
import re
from typing import ClassVar

from meridian.lib.harness.common import (
    categorize_stream_event,
    extract_codex_report,
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
from meridian.lib.harness.session_detection import resolve_codex_primary_session_id
from meridian.lib.safety.permissions import PermissionConfig
from meridian.lib.core.types import HarnessId, SpawnId


class CodexAdapter(BaseHarnessAdapter):
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
    BASE_COMMAND: ClassVar[tuple[str, ...]] = ("codex", "exec", "--json")
    PRIMARY_BASE_COMMAND: ClassVar[tuple[str, ...]] = ("codex",)
    EVENT_CATEGORY_MAP: ClassVar[dict[str, str]] = {
        "response.completed": "lifecycle",
        "response.output_text.delta": "assistant",
        "response.reasoning_summary.delta": "thinking",
        "tool.call.started": "tool-use",
        "tool.call.completed": "tool-use",
        "error": "error",
    }
    SESSION_ID_KEYS: ClassVar[tuple[str, ...]] = (
        "session_id",
        "sessionId",
        "sessionID",
        "conversation_id",
        "conversationId",
        "thread_id",
        "threadId",
    )
    SESSION_ID_TEXT_PATTERNS: ClassVar[tuple[re.Pattern[str], ...]] = (
        re.compile(r"\bcodex\s+resume\s+([A-Za-z0-9][A-Za-z0-9._:-]{5,})\b", re.IGNORECASE),
        re.compile(r"\bresume\s+([A-Za-z0-9][A-Za-z0-9._:-]{5,})\b", re.IGNORECASE),
    )

    @property
    def id(self) -> HarnessId:
        return HarnessId("codex")

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities(
            supports_stream_events=True,
            supports_stdin_prompt=True,
            supports_session_resume=True,
            supports_native_skills=True,
            supports_programmatic_tools=False,
            supports_primary_launch=True,
            reference_input_mode="paths",
        )

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        harness_session_id = (run.continue_harness_session_id or "").strip()
        if run.interactive:
            base_command = (
                ("codex", "resume", harness_session_id)
                if harness_session_id
                else self.PRIMARY_BASE_COMMAND
            )
            # Prompt injection here is a compatibility workaround: Codex does
            # not expose a true system prompt channel, so Meridian appends a
            # user-visible guard for fresh sessions only.
            guarded_prompt = run.prompt
            if guarded_prompt and not harness_session_id:
                guarded_prompt = f"{guarded_prompt}\n\nDO NOT DO ANYTHING. WAIT FOR USER INPUT."
            command_run = (
                run.model_copy(update={"prompt": guarded_prompt})
                if guarded_prompt != run.prompt
                else run
            )
        else:
            base_command = (
                ("codex", "exec", "--json", "resume", harness_session_id)
                if harness_session_id
                else self.BASE_COMMAND
            )
            # Codex supports prompt-from-stdin via "-" and this avoids argv length limits.
            command_run = run.model_copy(update={"prompt": "-"})
            # Codex -o writes the agent's final response to a file, giving us a clean
            # report without fragile JSONL parsing.
            if run.report_output_path:
                command_run = command_run.model_copy(
                    update={
                        "extra_args": command_run.extra_args + ("-o", run.report_output_path),
                    },
                )
        return build_harness_command(
            base_command=base_command,
            prompt_mode=self.PROMPT_MODE,
            run=command_run,
            strategies=self.STRATEGIES,
            perms=perms,
            harness_id=self.id,
        )

    def mcp_config(self, run: SpawnParams) -> McpConfig | None:
        # MCP injection is off by default — agents use the CLI instead.
        # Users who want always-on MCP can configure it in their harness settings.
        return None

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
        _ = started_at_local_iso
        return resolve_codex_primary_session_id(repo_root, started_at_epoch)

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_session_id_from_artifacts_with_patterns(
            artifacts,
            spawn_id,
            json_keys=self.SESSION_ID_KEYS,
            text_patterns=self.SESSION_ID_TEXT_PATTERNS,
        )

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_codex_report(artifacts, spawn_id)
