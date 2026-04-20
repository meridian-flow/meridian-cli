"""OpenCode CLI harness adapter."""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from meridian.lib.core.domain import TokenUsage
from meridian.lib.core.types import SpawnId
from meridian.lib.harness.adapter import (
    ArtifactStore,
    BaseHarnessAdapter,
    HarnessCapabilities,
    McpConfig,
    PermissionResolver,
    RunPromptPolicy,
    SpawnParams,
)
from meridian.lib.harness.bundle import HarnessBundle, register_harness_bundle
from meridian.lib.harness.common import (
    extract_opencode_report,
    extract_session_id_from_artifacts_with_patterns,
    extract_usage_from_artifacts,
)
from meridian.lib.harness.connections.opencode_http import OpenCodeConnection
from meridian.lib.harness.extractors.opencode import OPENCODE_EXTRACTOR
from meridian.lib.harness.ids import HarnessId, TransportId
from meridian.lib.harness.launch_spec import OpenCodeLaunchSpec
from meridian.lib.harness.launch_types import PromptPolicy, SessionSeed
from meridian.lib.harness.opencode_storage import resolve_opencode_session_file
from meridian.lib.harness.projections.project_opencode_subprocess import (
    project_opencode_spec_to_cli_args,
)
from meridian.lib.launch.constants import (
    BASE_COMMAND_OPENCODE_SUBPROCESS,
    PRIMARY_BASE_COMMAND_OPENCODE,
)
from meridian.lib.platform import get_home_path
from meridian.lib.safety.permissions import PermissionConfig

logger = logging.getLogger(__name__)

OPENCODE_SESSION_CREATED_RE = re.compile(
    r"^\w+\s+(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\s+\+\d+ms\s+"
    r"service=session\s+id=(?P<session_id>\S+)\s+.*?\bdirectory=(?P<directory>\S+)\b.*\bcreated\b"
)


def _strip_opencode_prefix(model: str) -> str:
    return model[len("opencode-") :] if model.startswith("opencode-") else model


def _normalize_opencode_model(model: str) -> str:
    stripped = _strip_opencode_prefix(model.strip())
    provider, separator, model_name = stripped.partition("/")
    if not separator:
        return stripped
    provider = provider.strip()
    model_name = model_name.strip()
    if not provider or not model_name:
        return stripped
    return f"{provider}/{model_name}"


def _detect_primary_session_id(
    repo_root: Path,
    started_at_epoch: float,
    started_at_local_iso: str,
) -> str | None:
    logs_root = get_home_path() / ".local" / "share" / "opencode" / "log"
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
    opencode_logs = get_home_path() / ".local" / "share" / "opencode" / "log"
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


class OpenCodeAdapter(BaseHarnessAdapter[OpenCodeLaunchSpec]):
    """SubprocessHarness implementation for `opencode`."""

    BASE_COMMAND: ClassVar[tuple[str, ...]] = BASE_COMMAND_OPENCODE_SUBPROCESS
    PRIMARY_BASE_COMMAND: ClassVar[tuple[str, ...]] = PRIMARY_BASE_COMMAND_OPENCODE
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
    _CONSUMED_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "prompt",
            "model",
            "effort",
            "skills",
            "agent",
            "adhoc_agent_payload",
            "extra_args",
            "repo_root",
            "interactive",
            "continue_harness_session_id",
            "continue_fork",
            "mcp_tools",
        }
    )
    _EXPLICITLY_IGNORED_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"appended_system_prompt", "report_output_path"}
    )

    @property
    def id(self) -> HarnessId:
        return HarnessId.OPENCODE

    @property
    def consumed_fields(self) -> frozenset[str]:
        return self._CONSUMED_FIELDS

    @property
    def explicitly_ignored_fields(self) -> frozenset[str]:
        return self._EXPLICITLY_IGNORED_FIELDS

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities(
            supports_stream_events=True,
            supports_stdin_prompt=True,
            supports_session_resume=True,
            supports_session_fork=True,
            supports_native_skills=True,
            supports_primary_launch=True,
        )

    def run_prompt_policy(self) -> RunPromptPolicy:
        return RunPromptPolicy()

    def resolve_launch_spec(
        self,
        run: SpawnParams,
        perms: PermissionResolver,
    ) -> OpenCodeLaunchSpec:
        normalized_model: str | None = None
        if run.model:
            normalized_model = _normalize_opencode_model(str(run.model))
        continue_session_id = (run.continue_harness_session_id or "").strip() or None
        use_prompt_skill_channel = self.run_prompt_policy().include_skills
        projected_skills = () if use_prompt_skill_channel else run.skills
        return OpenCodeLaunchSpec(
            model=normalized_model,
            effort=run.effort,
            prompt=run.prompt,
            continue_session_id=continue_session_id,
            continue_fork=run.continue_fork and continue_session_id is not None,
            permission_resolver=perms,
            extra_args=run.extra_args,
            interactive=run.interactive,
            mcp_tools=run.mcp_tools,
            agent_name=run.agent,
            skills=projected_skills,
        )

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        spec = self.resolve_launch_spec(run, perms)
        base_command = self.PRIMARY_BASE_COMMAND if spec.interactive else self.BASE_COMMAND
        return project_opencode_spec_to_cli_args(spec, base_command=base_command)

    def mcp_config(self, run: SpawnParams) -> McpConfig | None:
        # MCP injection is off by default — agents use the CLI instead.
        # Users who want always-on MCP can configure it in their harness settings.
        return None

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        if config.opencode_permission_override:
            return {"OPENCODE_PERMISSION": config.opencode_permission_override}
        return {}

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def seed_session(
        self,
        *,
        is_resume: bool,
        harness_session_id: str,
        passthrough_args: tuple[str, ...],
    ) -> SessionSeed:
        _ = is_resume, passthrough_args
        normalized_harness_session_id = harness_session_id.strip()
        if not normalized_harness_session_id:
            return SessionSeed()
        # Resume and fork both seed from an existing harness session id.
        return SessionSeed(session_id=normalized_harness_session_id)

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

    def resolve_session_file(self, *, repo_root: Path, session_id: str) -> Path | None:
        _ = repo_root
        return resolve_opencode_session_file(session_id=session_id)

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


register_harness_bundle(
    HarnessBundle(
        harness_id=HarnessId.OPENCODE,
        adapter=OpenCodeAdapter(),
        spec_cls=OpenCodeLaunchSpec,
        extractor=OPENCODE_EXTRACTOR,
        connections={TransportId.STREAMING: OpenCodeConnection},
    )
)
