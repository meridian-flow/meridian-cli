"""Harness adapter contracts and shared data models."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Generic, Literal, Protocol, TypeVar, cast, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.core.conversation import Conversation
from meridian.lib.core.domain import TokenUsage
from meridian.lib.core.types import ArtifactKey, ModelId, SpawnId
from meridian.lib.harness.ids import HarnessId
from meridian.lib.harness.launch_types import PromptPolicy, SessionSeed
from meridian.lib.launch.launch_types import (
    PermissionResolver,
    PreflightResult,
    ResolvedLaunchSpec,
    SpecT,
)
from meridian.lib.safety.permissions import PermissionConfig

AdapterSpecT = TypeVar("AdapterSpecT", bound=ResolvedLaunchSpec, covariant=True)
logger = logging.getLogger(__name__)


def _empty_metadata() -> dict[str, object]:
    return {}


def _empty_env_overrides() -> dict[str, str]:
    return {}


def _coerce_permission_flags(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, tuple):
        tuple_tokens = cast("tuple[object, ...]", raw)
        return tuple(str(token) for token in tuple_tokens)
    if isinstance(raw, list):
        list_tokens = cast("list[object]", raw)
        return tuple(str(token) for token in list_tokens)
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, Iterable):
        iterable_tokens = cast("Iterable[object]", raw)
        return tuple(str(token) for token in iterable_tokens)
    raise TypeError(f"Permission resolver flags must be iterable, got {type(raw).__name__}")


def _permission_flags_for_harness(
    *,
    harness_id: HarnessId,
    config: PermissionConfig,
) -> tuple[str, ...]:
    if config.approval == "yolo":
        if harness_id == HarnessId.CLAUDE:
            return ("--dangerously-skip-permissions",)
        if harness_id == HarnessId.CODEX:
            return ("--dangerously-bypass-approvals-and-sandbox",)
        return ()

    if config.approval == "auto":
        if harness_id == HarnessId.CLAUDE:
            return ("--permission-mode", "acceptEdits")
        if harness_id == HarnessId.CODEX:
            return ("--full-auto",)
        return ()

    if config.approval == "confirm":
        if harness_id == HarnessId.CLAUDE:
            return ("--permission-mode", "default")
        if harness_id == HarnessId.CODEX:
            return ("--ask-for-approval", "untrusted")
        return ()

    if harness_id == HarnessId.CODEX and config.sandbox != "default":
        return ("--sandbox", config.sandbox)
    return ()


def _strip_claude_tool_flags(flags: tuple[str, ...]) -> tuple[str, ...]:
    filtered: list[str] = []
    index = 0
    while index < len(flags):
        token = flags[index]
        if token in {"--allowedTools", "--disallowedTools"}:
            index += 2
            continue
        filtered.append(token)
        index += 1
    return tuple(filtered)


def resolve_permission_flags(
    permission_resolver: PermissionResolver,
    harness_id: HarnessId,
) -> tuple[str, ...]:
    """Resolve projected permission flags for one harness."""

    base_flags = list(
        _permission_flags_for_harness(harness_id=harness_id, config=permission_resolver.config)
    )
    resolver_flags = _coerce_permission_flags(permission_resolver.resolve_flags())
    if harness_id != HarnessId.CLAUDE:
        stripped = _strip_claude_tool_flags(resolver_flags)
        if harness_id == HarnessId.CODEX and "--disallowedTools" in resolver_flags:
            logger.warning(
                "Codex does not support disallowed-tools; "
                "falling back to sandbox/approval flags."
            )
        resolver_flags = stripped
    base_flags.extend(resolver_flags)
    return tuple(base_flags)


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
    model: ModelId | None = None
    effort: str | None = None
    skills: tuple[str, ...] = ()
    agent: str | None = None
    # Pre-built ad-hoc native-agent payload. Empty string when not used.
    adhoc_agent_payload: str = ""
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
class ArtifactStore(Protocol):
    """Artifact access used for usage/session extraction."""

    def get(self, key: ArtifactKey) -> bytes: ...

    def exists(self, key: ArtifactKey) -> bool: ...


@runtime_checkable
class SpawnExtractor(Protocol):
    """Artifact extraction interface for spawn finalization."""

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage: ...

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None: ...

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None: ...


@runtime_checkable
class HarnessAdapter(Protocol, Generic[AdapterSpecT]):
    """Typed harness adapter contract."""

    @property
    def id(self) -> HarnessId: ...

    @property
    def consumed_fields(self) -> frozenset[str]: ...

    @property
    def explicitly_ignored_fields(self) -> frozenset[str]: ...

    @property
    def handled_fields(self) -> frozenset[str]: ...

    def resolve_launch_spec(
        self, run: SpawnParams, perms: PermissionResolver
    ) -> AdapterSpecT: ...

    def preflight(
        self,
        *,
        execution_cwd: Path,
        child_cwd: Path,
        passthrough_args: tuple[str, ...],
    ) -> PreflightResult: ...


@runtime_checkable
class SubprocessHarness(HarnessAdapter[ResolvedLaunchSpec], Protocol):
    """Protocol for subprocess-launching harness behavior."""

    @property
    def capabilities(self) -> HarnessCapabilities: ...

    def run_prompt_policy(self) -> RunPromptPolicy: ...

    def build_adhoc_agent_payload(self, *, name: str, description: str, prompt: str) -> str: ...

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]: ...

    def mcp_config(self, run: SpawnParams) -> McpConfig | None: ...

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]: ...

    def blocked_child_env_vars(self) -> frozenset[str]: ...

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage: ...

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None: ...

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None: ...

    def resolve_session_file(self, *, repo_root: Path, session_id: str) -> Path | None: ...

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


@runtime_checkable
class InProcessHarness(Protocol):
    """Protocol for in-process harness execution behavior."""

    @property
    def id(self) -> HarnessId: ...

    @property
    def capabilities(self) -> HarnessCapabilities: ...

    async def execute(self, *, prompt: str, model: ModelId, **kwargs: Any) -> SpawnResult: ...


@runtime_checkable
class ConversationExtractingHarness(Protocol):
    """Optional protocol for harnesses that provide conversation extraction."""

    def extract_conversation(
        self, artifacts: ArtifactStore, spawn_id: SpawnId
    ) -> Conversation | None: ...


class BaseHarnessAdapter(Generic[SpecT], ABC):
    """Base adapter with contract enforcement and optional helper defaults."""

    @property
    @abstractmethod
    def id(self) -> HarnessId:
        """Harness identifier for this adapter."""
        ...

    @property
    @abstractmethod
    def consumed_fields(self) -> frozenset[str]:
        """SpawnParams fields actively consumed by this adapter."""
        ...

    @property
    @abstractmethod
    def explicitly_ignored_fields(self) -> frozenset[str]:
        """SpawnParams fields deliberately ignored by this adapter."""
        ...

    @property
    def handled_fields(self) -> frozenset[str]:
        return self.consumed_fields | self.explicitly_ignored_fields

    @abstractmethod
    def resolve_launch_spec(self, run: SpawnParams, perms: PermissionResolver) -> SpecT:
        """Resolve typed launch spec from generic spawn parameters."""
        ...

    def preflight(
        self,
        *,
        execution_cwd: Path,
        child_cwd: Path,
        passthrough_args: tuple[str, ...],
    ) -> PreflightResult:
        _ = execution_cwd, child_cwd
        return PreflightResult.build(expanded_passthrough_args=passthrough_args)

    def run_prompt_policy(self) -> RunPromptPolicy:
        return RunPromptPolicy()

    def build_adhoc_agent_payload(self, *, name: str, description: str, prompt: str) -> str:
        _ = name, description, prompt
        return ""

    def fork_session(self, source_session_id: str) -> str:
        """Fork one harness session and return the new session ID."""

        _ = source_session_id
        raise NotImplementedError

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

    def mcp_config(self, run: SpawnParams) -> McpConfig | None:
        _ = run
        return None

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        _ = artifacts, spawn_id
        return None

    def resolve_session_file(self, *, repo_root: Path, session_id: str) -> Path | None:
        _ = repo_root, session_id
        return None


def resolve_mcp_config(adapter: SubprocessHarness, run: SpawnParams) -> McpConfig | None:
    """Resolve adapter MCP config."""

    return adapter.mcp_config(run)


# Temporary alias while downstream tests migrate to the new base-class name.
BaseSubprocessHarness = BaseHarnessAdapter
