"""Prepared spawn planning DTOs."""

from pydantic import BaseModel, ConfigDict

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
    reference_files: tuple[str, ...]
    template_vars: dict[str, str]
    mcp_tools: tuple[str, ...]
    session_agent: str
    session_agent_path: str
    session: SessionContinuation
    execution: ExecutionPolicy
    appended_system_prompt: str | None = None
    cli_command: tuple[str, ...]
    warning: str | None = None


__all__ = ["ExecutionPolicy", "PreparedSpawnPlan", "SessionContinuation"]
