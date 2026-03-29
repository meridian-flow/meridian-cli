"""Prepared spawn planning DTOs."""

from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.harness.adapter import PermissionResolver
from meridian.lib.safety.permissions import PermissionConfig


class ExecutionPolicy(BaseModel):
    """Execution-time controls for one spawn run."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    timeout_secs: float | None = None
    kill_grace_secs: float = 30.0
    max_retries: int = 0
    retry_backoff_secs: float = 2.0
    permission_config: PermissionConfig
    permission_resolver: PermissionResolver
    allowed_tools: tuple[str, ...] = ()


class SessionContinuation(BaseModel):
    """Continuation options for harness session reuse."""

    model_config = ConfigDict(frozen=True)

    harness_session_id: str | None = None
    continue_fork: bool = False


class PreparedSpawnPlan(BaseModel):
    """Fully prepared spawn plan consumed by execution."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    model: str
    harness_id: str
    prompt: str
    agent_name: str | None
    skills: tuple[str, ...]
    skill_paths: tuple[str, ...]
    agent_path: str = ""
    agent_source: str | None = None
    skill_sources: dict[str, str] = Field(default_factory=dict)
    bootstrap_required_items: tuple[str, ...] = ()
    bootstrap_missing_items: tuple[str, ...] = ()
    reference_files: tuple[str, ...]
    template_vars: dict[str, str]
    context_from_resolved: tuple[str, ...] = ()
    mcp_tools: tuple[str, ...]
    session_agent: str
    session_agent_path: str
    session: SessionContinuation
    execution: ExecutionPolicy
    adhoc_agent_payload: str = ""
    appended_system_prompt: str | None = None
    autocompact: int | None = None
    cli_command: tuple[str, ...]
    warning: str | None = None
    passthrough_args: tuple[str, ...] = ()


__all__ = ["ExecutionPolicy", "PreparedSpawnPlan", "SessionContinuation"]
