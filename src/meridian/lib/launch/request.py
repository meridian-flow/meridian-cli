"""Raw launch request DTOs persisted across prepare/execute boundaries."""

from pydantic import BaseModel, ConfigDict, Field


def _empty_template_vars() -> dict[str, str]:
    return {}


def _empty_agent_metadata() -> dict[str, str]:
    return {}


class RetryPolicy(BaseModel):
    """Retry configuration for spawn execution."""

    model_config = ConfigDict(frozen=True)

    max_attempts: int = 1
    backoff_secs: float = 2.0


class ExecutionBudget(BaseModel):
    """Resource limits for spawn execution."""

    model_config = ConfigDict(frozen=True)

    timeout_secs: int | None = None
    kill_grace_secs: int = 30


class SessionRequest(BaseModel):
    """Session continuation options carried across prepare/execute boundaries."""

    model_config = ConfigDict(frozen=True)

    continue_chat_id: str | None = None
    requested_harness_session_id: str | None = None
    continue_fork: bool = False
    source_execution_cwd: str | None = None
    forked_from_chat_id: str | None = None
    continue_harness: str | None = None
    continue_source_tracked: bool = False
    continue_source_ref: str | None = None


class SpawnRequest(BaseModel):
    """Raw spawn request used to reconstruct launch composition at execute time."""

    model_config = ConfigDict(frozen=True)

    # Prompt / agent / skills
    prompt: str
    model: str | None = None
    harness: str | None = None
    agent: str | None = None
    skills: tuple[str, ...] = ()

    # Harness shape
    extra_args: tuple[str, ...] = ()
    mcp_tools: tuple[str, ...] = ()
    sandbox: str | None = None
    approval: str | None = None
    allowed_tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    autocompact: bool | None = None
    effort: str | None = None

    # Execution policy (nested)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    budget: ExecutionBudget = Field(default_factory=ExecutionBudget)

    # Session intent (nested)
    session: SessionRequest = Field(default_factory=SessionRequest)

    # Context plumbing
    context_from: str | None = None
    reference_files: tuple[str, ...] = ()
    template_vars: dict[str, str] = Field(default_factory=_empty_template_vars)

    # Routing & metadata
    work_id_hint: str | None = None
    agent_metadata: dict[str, str] = Field(default_factory=_empty_agent_metadata)


class LaunchRuntime(BaseModel):
    """Runtime context known by the driving adapter, not provided by callers."""

    model_config = ConfigDict(frozen=True)

    launch_mode: str
    unsafe_no_permissions: bool = False
    debug: bool = False
    harness_command_override: str | None = None
    report_output_path: str | None = None
    state_root: str
    project_paths_repo_root: str
    project_paths_execution_cwd: str


__all__ = [
    "ExecutionBudget",
    "LaunchRuntime",
    "RetryPolicy",
    "SessionRequest",
    "SpawnRequest",
]
