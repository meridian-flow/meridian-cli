"""OpenCode CLI harness adapter."""

import re
import logging
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from meridian.lib.harness.common import (
    extract_opencode_report,
    extract_session_id_from_artifacts_with_patterns,
    extract_usage_from_artifacts,
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
    BaseSubprocessHarness,
    HarnessCapabilities,
    McpConfig,
    PermissionResolver,
    RunPromptPolicy,
    SpawnParams,
)
from meridian.lib.harness.launch_types import PromptPolicy
from meridian.lib.safety.permissions import PermissionConfig, opencode_permission_json
from meridian.lib.core.domain import TokenUsage
from meridian.lib.core.types import HarnessId, SpawnId

logger = logging.getLogger(__name__)

OPENCODE_SESSION_CREATED_RE = re.compile(
    r"^\w+\s+(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\s+\+\d+ms\s+"
    r"service=session\s+id=(?P<session_id>\S+)\s+.*?\bdirectory=(?P<directory>\S+)\b.*\bcreated\b"
)


def _strip_opencode_prefix(model: str) -> str:
    return model[len("opencode-") :] if model.startswith("opencode-") else model


def _opencode_model_transform(value: object, args: list[str]) -> None:
    if value is None:
        return
    args.extend(["--model", _strip_opencode_prefix(str(value))])


def _detect_primary_session_id(
    repo_root: Path,
    started_at_epoch: float,
    started_at_local_iso: str,
) -> str | None:
    logs_root = Path.home() / ".local" / "share" / "opencode" / "log"
    if not logs_root.is_dir():
        return None

    resolved_repo = repo_root.resolve()
    matches: list[tuple[str, str]] = []
    for candidate in logs_root.glob("*.log"):
        try:
            modified_at = candidate.stat().st_mtime
        except OSError:
            continue
        if modified_at + 1 < started_at_epoch:
            continue
        try:
            lines = candidate.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            logger.debug("Failed to read opencode log %s", candidate, exc_info=True)
            continue
        for line in lines:
            match = OPENCODE_SESSION_CREATED_RE.match(line)
            if match is None:
                continue
            timestamp = match.group("ts")
            if timestamp < started_at_local_iso:
                continue
            directory = match.group("directory")
            try:
                directory_matches = Path(directory).expanduser().resolve() == resolved_repo
            except OSError:
                continue
            if not directory_matches:
                continue
            session_id = match.group("session_id").strip()
            if session_id:
                matches.append((timestamp, session_id))

    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]


def _owns_session(repo_root: Path, session_ref: str) -> bool:
    normalized = session_ref.strip()
    if not normalized:
        return False

    resolved_repo = repo_root.resolve()
    opencode_logs = Path.home() / ".local" / "share" / "opencode" / "log"
    if not opencode_logs.is_dir():
        return False

    for candidate in opencode_logs.glob("*.log"):
        try:
            lines = candidate.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            match = OPENCODE_SESSION_CREATED_RE.match(line)
            if match is None:
                continue
            if match.group("session_id").strip() != normalized:
                continue
            directory = match.group("directory")
            try:
                directory_matches = Path(directory).expanduser().resolve() == resolved_repo
            except OSError:
                continue
            if directory_matches:
                return True

    return False


class OpenCodeAdapter(BaseSubprocessHarness):
    """SubprocessHarness implementation for `opencode`."""

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
        return HarnessId.OPENCODE

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

    def run_prompt_policy(self) -> RunPromptPolicy:
        return RunPromptPolicy()

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
        if config.tier is None:
            return {}
        return {"OPENCODE_PERMISSION": opencode_permission_json(config.tier)}

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
        return _detect_primary_session_id(repo_root, started_at_epoch, local_iso)

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
        return extract_opencode_report(artifacts, spawn_id)
