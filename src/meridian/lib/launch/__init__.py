"""Public launch API."""

from pathlib import Path

from meridian.lib.harness.registry import HarnessRegistry

from .command import (
    build_harness_command,
    build_launch_env,
    normalize_system_prompt_passthrough_args,
)
from .plan import (
    ResolvedPrimaryLaunchPlan,
    resolve_primary_launch_plan,
)
from .process import (
    ProcessOutcome,
    run_harness_process,
)
from .resolve import (
    ResolvedPolicies,
    ResolvedSkills,
    load_agent_profile_with_fallback,
    resolve_harness,
    resolve_policies,
    resolve_skills_from_profile,
)
from .types import LaunchRequest, LaunchResult, PrimarySessionMetadata, build_primary_prompt


def launch_primary(
    *,
    repo_root: Path,
    request: LaunchRequest,
    harness_registry: HarnessRegistry,
) -> LaunchResult:
    """Launch the primary agent process and wait for exit."""

    plan = resolve_primary_launch_plan(
        repo_root=repo_root,
        request=request,
        harness_registry=harness_registry,
    )

    if request.dry_run:
        return LaunchResult(
            command=plan.command,
            exit_code=0,
            continue_ref=None,
        )

    outcome = run_harness_process(plan, harness_registry)
    continue_ref = outcome.resolved_harness_session_id.strip() or None

    return LaunchResult(
        command=outcome.command,
        exit_code=outcome.exit_code,
        continue_ref=continue_ref,
    )


__all__ = [
    "LaunchRequest",
    "LaunchResult",
    "PrimarySessionMetadata",
    "ProcessOutcome",
    "ResolvedPolicies",
    "ResolvedPrimaryLaunchPlan",
    "ResolvedSkills",
    "build_harness_command",
    "build_launch_env",
    "build_primary_prompt",
    "launch_primary",
    "load_agent_profile_with_fallback",
    "normalize_system_prompt_passthrough_args",
    "resolve_harness",
    "resolve_policies",
    "resolve_primary_launch_plan",
    "resolve_skills_from_profile",
    "run_harness_process",
]
