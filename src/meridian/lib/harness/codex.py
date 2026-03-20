"""Codex CLI harness adapter."""

import json
import logging
import re
from pathlib import Path
from typing import ClassVar, cast

from meridian.lib.core.domain import TokenUsage
from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.adapter import (
    ArtifactStore,
    BaseSubprocessHarness,
    HarnessCapabilities,
    McpConfig,
    PermissionResolver,
    RunPromptPolicy,
    SpawnParams,
)
from meridian.lib.harness.common import (
    FlagEffect,
    FlagStrategy,
    PromptMode,
    StrategyMap,
    build_harness_command,
    extract_codex_report,
    extract_session_id_from_artifacts_with_patterns,
    extract_usage_from_artifacts,
)
from meridian.lib.harness.launch_types import PromptPolicy
from meridian.lib.safety.permissions import PermissionConfig

logger = logging.getLogger(__name__)

CODEX_ROLLOUT_FILENAME_RE = re.compile(
    r"^rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-(?P<session_id>[0-9a-fA-F-]{36})\.jsonl$"
)


def _codex_thinking_transform(value: object, args: list[str]) -> None:
    normalized = str(value).strip()
    if not normalized:
        return
    args.extend(["-c", f'model_reasoning_effort="{normalized}"'])


def _resolve_rollout_session_id(path: Path, resolved_repo: Path) -> str | None:
    session_id: str | None = None
    saw_assistant_message = False
    saw_turn_aborted = False

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            try:
                raw_payload_obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw_payload_obj, dict):
                continue
            payload_obj = cast("dict[str, object]", raw_payload_obj)
            payload_type = payload_obj.get("type")
            if not isinstance(payload_type, str):
                continue

            if payload_type == "session_meta":
                raw_payload = payload_obj.get("payload")
                if not isinstance(raw_payload, dict):
                    continue
                payload = cast("dict[str, object]", raw_payload)
                candidate_session_id = payload.get("id")
                cwd = payload.get("cwd")
                if not isinstance(candidate_session_id, str) or not candidate_session_id.strip():
                    continue
                if not isinstance(cwd, str):
                    continue
                try:
                    cwd_matches = Path(cwd).expanduser().resolve() == resolved_repo
                except OSError:
                    continue
                if not cwd_matches:
                    return None
                session_id = candidate_session_id.strip()
                continue

            if payload_type == "response_item":
                raw_payload = payload_obj.get("payload")
                if not isinstance(raw_payload, dict):
                    continue
                payload = cast("dict[str, object]", raw_payload)
                if payload.get("type") == "message" and payload.get("role") == "assistant":
                    saw_assistant_message = True
                continue

            if payload_type == "event_msg":
                raw_payload = payload_obj.get("payload")
                payload = (
                    cast("dict[str, object] | None", raw_payload)
                    if isinstance(raw_payload, dict)
                    else None
                )
                if payload is not None and payload.get("type") == "turn_aborted":
                    saw_turn_aborted = True
                continue

            if payload_type == "turn_aborted":
                saw_turn_aborted = True

    if session_id is None:
        return None
    if saw_turn_aborted and not saw_assistant_message:
        return None
    return session_id


def _detect_primary_session_id(repo_root: Path, started_at_epoch: float) -> str | None:
    sessions_root = Path.home() / ".codex" / "sessions"
    if not sessions_root.is_dir():
        return None

    resolved_repo = repo_root.resolve()
    candidates: list[tuple[float, Path]] = []
    for candidate in sessions_root.rglob("rollout-*.jsonl"):
        if CODEX_ROLLOUT_FILENAME_RE.match(candidate.name) is None:
            continue
        try:
            modified_at = candidate.stat().st_mtime
        except OSError:
            continue
        if modified_at + 1 < started_at_epoch:
            continue
        candidates.append((modified_at, candidate))

    for _, path in sorted(candidates, key=lambda item: item[0], reverse=True):
        try:
            resolved = _resolve_rollout_session_id(path, resolved_repo)
        except OSError:
            logger.debug("Failed to read codex rollout %s", path, exc_info=True)
            continue
        if resolved is not None:
            return resolved
    return None


def _compose_inline_launch_prompt(*, prompt: str, skill_injection: str | None) -> str:
    sections: list[str] = []
    injected = (skill_injection or "").strip()
    if injected:
        sections.append(injected)
    prompt_text = prompt.strip()
    if prompt_text:
        sections.append(prompt_text)
    return "\n\n".join(sections)


def _owns_session(repo_root: Path, session_ref: str) -> bool:
    normalized = session_ref.strip()
    if not normalized:
        return False

    resolved_repo = repo_root.resolve()
    codex_root = Path.home() / ".codex" / "sessions"
    if not codex_root.is_dir():
        return False

    for candidate in codex_root.rglob(f"rollout-*-{normalized}.jsonl"):
        if CODEX_ROLLOUT_FILENAME_RE.match(candidate.name) is None:
            continue
        try:
            with candidate.open("r", encoding="utf-8", errors="ignore") as handle:
                for _ in range(5):
                    line = handle.readline()
                    if not line:
                        break
                    raw_payload_obj = json.loads(line)
                    if not isinstance(raw_payload_obj, dict):
                        continue
                    payload_obj = cast("dict[str, object]", raw_payload_obj)
                    if payload_obj.get("type") != "session_meta":
                        continue
                    raw_payload = payload_obj.get("payload")
                    if not isinstance(raw_payload, dict):
                        continue
                    payload = cast("dict[str, object]", raw_payload)
                    session_id = payload.get("id")
                    cwd = payload.get("cwd")
                    if not isinstance(session_id, str) or session_id.strip() != normalized:
                        continue
                    if not isinstance(cwd, str):
                        continue
                    try:
                        cwd_matches = Path(cwd).expanduser().resolve() == resolved_repo
                    except OSError:
                        continue
                    if cwd_matches:
                        return True
        except (OSError, json.JSONDecodeError):
            continue

    return False


class CodexAdapter(BaseSubprocessHarness):
    """SubprocessHarness implementation for `codex`."""

    STRATEGIES: ClassVar[StrategyMap] = {
        "model": FlagStrategy(effect=FlagEffect.CLI_FLAG, cli_flag="--model"),
        "thinking": FlagStrategy(
            effect=FlagEffect.TRANSFORM,
            transform=_codex_thinking_transform,
        ),
        "agent": FlagStrategy(effect=FlagEffect.DROP),
        "skills": FlagStrategy(effect=FlagEffect.DROP),
        "continue_harness_session_id": FlagStrategy(effect=FlagEffect.DROP),
        "continue_fork": FlagStrategy(effect=FlagEffect.DROP),
        "appended_system_prompt": FlagStrategy(effect=FlagEffect.DROP),
    }
    PROMPT_MODE: ClassVar[PromptMode] = PromptMode.POSITIONAL
    BASE_COMMAND: ClassVar[tuple[str, ...]] = ("codex", "exec", "--json")
    PRIMARY_BASE_COMMAND: ClassVar[tuple[str, ...]] = ("codex",)
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
        return HarnessId.CODEX

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

    def run_prompt_policy(self) -> RunPromptPolicy:
        return RunPromptPolicy()

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
                        "extra_args": (*command_run.extra_args, "-o", run.report_output_path),
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

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage:
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
        return PromptPolicy(
            prompt=_compose_inline_launch_prompt(prompt=prompt, skill_injection=skill_injection),
            # Keep passthrough system-prompt fragments on the inline injection path.
            skill_injection="",
        )

    def detect_primary_session_id(
        self,
        *,
        repo_root: Path,
        started_at_epoch: float,
        started_at_local_iso: str | None,
    ) -> str | None:
        _ = started_at_local_iso
        return _detect_primary_session_id(repo_root, started_at_epoch)

    def resolve_session_file(self, *, repo_root: Path, session_id: str) -> Path | None:
        _ = repo_root
        normalized_session_id = session_id.strip()
        if not normalized_session_id:
            return None

        sessions_root = Path.home() / ".codex" / "sessions"
        if not sessions_root.is_dir():
            return None

        matches: list[tuple[float, Path]] = []
        for candidate in sessions_root.rglob(f"rollout-*-{normalized_session_id}.jsonl"):
            if CODEX_ROLLOUT_FILENAME_RE.match(candidate.name) is None:
                continue
            try:
                modified_at = candidate.stat().st_mtime
            except OSError:
                continue
            matches.append((modified_at, candidate))

        if not matches:
            return None

        matches.sort(key=lambda item: item[0], reverse=True)
        return matches[0][1]

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_session_id_from_artifacts_with_patterns(
            artifacts,
            spawn_id,
            json_keys=self.SESSION_ID_KEYS,
            text_patterns=self.SESSION_ID_TEXT_PATTERNS,
        )

    def owns_untracked_session(self, *, repo_root: Path, session_ref: str) -> bool:
        return _owns_session(repo_root, session_ref)

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_codex_report(artifacts, spawn_id)
