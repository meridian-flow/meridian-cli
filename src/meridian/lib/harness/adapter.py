"""Harness adapter protocol and shared data models."""

from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.core.domain import TokenUsage
from meridian.lib.harness.launch_types import PromptPolicy, SessionSeed
from meridian.lib.safety.permissions import PermissionConfig
from meridian.lib.core.types import ArtifactKey, HarnessId, ModelId, SpawnId


def _empty_metadata() -> dict[str, object]:
    return {}


def _empty_env_overrides() -> dict[str, str]:
    return {}


class HarnessCapabilities(BaseModel):
    """Feature flags for one harness implementation."""

    model_config = ConfigDict(frozen=True)

    supports_stream_events: bool = True
    supports_stdin_prompt: bool = False
    supports_session_resume: bool = False
    supports_session_fork: bool = False
    supports_native_skills: bool = False
    supports_native_agents: bool = False
    supports_programmatic_tools: bool = False
    supports_primary_launch: bool = False
    reference_input_mode: Literal["inline", "paths"] = "paths"


class HarnessNativeLayout(BaseModel):
    """Directories a harness reads agents/skills from natively."""

    model_config = ConfigDict(frozen=True)

    agents: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    global_agents: tuple[str, ...] = ()
    global_skills: tuple[str, ...] = ()


class RunPromptPolicy(BaseModel):
    """Adapter-owned policy for composing one run prompt."""

    model_config = ConfigDict(frozen=True)

    include_agent_body: bool = True
    include_skills: bool = True
    skill_injection_mode: Literal["none", "append-system-prompt"] = "none"


class SpawnParams(BaseModel):
    """Inputs required to launch one harness run."""

    model_config = ConfigDict(frozen=True)

    prompt: str
    model: ModelId
    skills: tuple[str, ...] = ()
    agent: str | None = None
    # Pre-built --agents JSON for Claude ad-hoc agent passthrough. Empty string when not used.
    adhoc_agent_json: str = ""
    extra_args: tuple[str, ...] = ()
    repo_root: str | None = None
    mcp_tools: tuple[str, ...] = ()
    interactive: bool = False
    continue_harness_session_id: str | None = None
    continue_fork: bool = False
    appended_system_prompt: str | None = None
    report_output_path: str | None = None


class McpConfig(BaseModel):
    """Harness-specific MCP wiring details for one run."""

    model_config = ConfigDict(frozen=True)

    command_args: tuple[str, ...] = ()
    env_overrides: dict[str, str] = Field(default_factory=_empty_env_overrides)
    claude_allowed_tools: tuple[str, ...] = ()


class StreamEvent(BaseModel):
    """Structured stream event parsed from harness output."""

    model_config = ConfigDict(frozen=True)

    event_type: str
    category: str
    raw_line: str
    text: str | None = None
    metadata: dict[str, object] = Field(default_factory=_empty_metadata)


class SpawnResult(BaseModel):
    """Result payload for one completed execution."""

    model_config = ConfigDict(frozen=True)

    status: str
    output: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    harness_session_id: str | None = None
    raw_response: dict[str, object] | None = None


@runtime_checkable
class PermissionResolver(Protocol):
    """Permission resolver provided by execution layer."""

    def resolve_flags(self, harness_id: HarnessId) -> list[str]: ...


@runtime_checkable
class ArtifactStore(Protocol):
    """Artifact access used for usage/session extraction."""

    def get(self, key: ArtifactKey) -> bytes: ...

    def exists(self, key: ArtifactKey) -> bool: ...


@runtime_checkable
class HarnessAdapter(Protocol):
    """Protocol for harness-specific launch/parsing/extraction behavior."""

    @property
    def id(self) -> HarnessId: ...

    @property
    def capabilities(self) -> HarnessCapabilities: ...

    def native_layout(self) -> HarnessNativeLayout | None: ...

    def run_prompt_policy(self) -> RunPromptPolicy: ...

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]: ...

    def mcp_config(self, run: SpawnParams) -> McpConfig | None: ...

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]: ...

    def blocked_child_env_vars(self) -> frozenset[str]: ...

    def parse_stream_event(self, line: str) -> StreamEvent | None: ...

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage: ...

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None: ...

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None: ...

    def seed_session(
        self,
        *,
        is_resume: bool,
        harness_session_id: str,
        passthrough_args: tuple[str, ...],
    ) -> SessionSeed: ...

    def filter_launch_content(
        self,
        *,
        prompt: str,
        skill_injection: str | None,
        is_resume: bool,
        harness_session_id: str,
    ) -> PromptPolicy: ...

    def detect_primary_session_id(
        self,
        *,
        repo_root: Path,
        started_at_epoch: float,
        started_at_local_iso: str | None,
    ) -> str | None: ...

    def owns_untracked_session(self, *, repo_root: Path, session_ref: str) -> bool:
        """Return True if this harness owns the given untracked session reference."""
        ...

    def extract_tasks(self, event: StreamEvent) -> list[dict[str, str]] | None:
        """Extract structured task updates from one stream event."""

        _ = event
        return None

    def extract_findings(self, event: StreamEvent) -> list[dict[str, str]] | None:
        """Extract structured findings from one stream event."""

        _ = event
        return None

    def extract_summary(self, output: str) -> str | None:
        """Extract a concise run summary from final output text."""

        _ = output
        return None


class BaseHarnessAdapter:
    """Base with default no-op implementations for optional adapter methods."""

    def native_layout(self) -> HarnessNativeLayout | None:
        return None

    def run_prompt_policy(self) -> RunPromptPolicy:
        return RunPromptPolicy()

    def owns_untracked_session(self, *, repo_root: Path, session_ref: str) -> bool:
        _ = repo_root, session_ref
        return False

    def blocked_child_env_vars(self) -> frozenset[str]:
        return frozenset()

    def seed_session(
        self,
        *,
        is_resume: bool,
        harness_session_id: str,
        passthrough_args: tuple[str, ...],
    ) -> SessionSeed:
        _ = is_resume, harness_session_id, passthrough_args
        return SessionSeed()

    def filter_launch_content(
        self,
        *,
        prompt: str,
        skill_injection: str | None,
        is_resume: bool,
        harness_session_id: str,
    ) -> PromptPolicy:
        _ = is_resume, harness_session_id
        return PromptPolicy(prompt=prompt, skill_injection=skill_injection)

    def detect_primary_session_id(
        self,
        *,
        repo_root: Path,
        started_at_epoch: float,
        started_at_local_iso: str | None,
    ) -> str | None:
        _ = repo_root, started_at_epoch, started_at_local_iso
        return None

    def extract_tasks(self, event: StreamEvent) -> list[dict[str, str]] | None:
        _ = event
        return None

    def extract_findings(self, event: StreamEvent) -> list[dict[str, str]] | None:
        _ = event
        return None

    def extract_summary(self, output: str) -> str | None:
        _ = output
        return None

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        _ = artifacts, spawn_id
        return None


def resolve_mcp_config(adapter: HarnessAdapter, run: SpawnParams) -> McpConfig | None:
    """Resolve adapter MCP config if the adapter implements the optional hook."""

    resolver = getattr(adapter, "mcp_config", None)
    if resolver is None:
        return None
    return resolver(run)
