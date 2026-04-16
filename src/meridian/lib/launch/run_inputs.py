"""Run-input aggregation stage for launch composition."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.types import ModelId
from meridian.lib.harness.adapter import SpawnParams


class ResolvedRunInputs(BaseModel):
    """Factory-owned run inputs used to derive spec/argv/env stages."""

    model_config = ConfigDict(frozen=True)

    prompt: str
    model: ModelId | None = None
    effort: str | None = None
    skills: tuple[str, ...] = ()
    agent: str | None = None
    adhoc_agent_payload: str = ""
    extra_args: tuple[str, ...] = ()
    repo_root: str | None = None
    mcp_tools: tuple[str, ...] = ()
    interactive: bool = False
    continue_harness_session_id: str | None = None
    continue_fork: bool = False
    appended_system_prompt: str | None = None
    report_output_path: str | None = None
    context_from_payload: str | None = None


def build_resolved_run_inputs(
    *,
    prompt: str,
    model: ModelId | None,
    effort: str | None,
    skills: tuple[str, ...],
    agent: str | None,
    adhoc_agent_payload: str,
    extra_args: tuple[str, ...],
    repo_root: str | None,
    mcp_tools: tuple[str, ...],
    continue_harness_session_id: str | None,
    continue_fork: bool = False,
    appended_system_prompt: str | None = None,
    report_output_path: str | None = None,
    interactive: bool = False,
    context_from_payload: str | None = None,
) -> ResolvedRunInputs:
    """Build the stage-owned run-input DTO from composed launch inputs."""

    return ResolvedRunInputs(
        prompt=prompt,
        model=model,
        effort=effort,
        skills=skills,
        agent=agent,
        adhoc_agent_payload=adhoc_agent_payload,
        extra_args=extra_args,
        repo_root=repo_root,
        mcp_tools=mcp_tools,
        interactive=interactive,
        continue_harness_session_id=continue_harness_session_id,
        continue_fork=continue_fork,
        appended_system_prompt=appended_system_prompt,
        report_output_path=report_output_path,
        context_from_payload=context_from_payload,
    )


def coerce_resolved_run_inputs(run_inputs: ResolvedRunInputs | SpawnParams) -> ResolvedRunInputs:
    """Normalize either DTO flavor into `ResolvedRunInputs`."""

    if isinstance(run_inputs, ResolvedRunInputs):
        return run_inputs
    return ResolvedRunInputs(**run_inputs.model_dump())


def to_spawn_params(run_inputs: ResolvedRunInputs | SpawnParams) -> SpawnParams:
    """Project stage-owned run inputs back to adapter launch params."""

    if isinstance(run_inputs, SpawnParams):
        return run_inputs
    payload = run_inputs.model_dump(exclude={"context_from_payload"})
    return SpawnParams(**payload)


__all__ = [
    "ResolvedRunInputs",
    "build_resolved_run_inputs",
    "coerce_resolved_run_inputs",
    "to_spawn_params",
]
