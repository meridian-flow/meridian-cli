"""Public launch API."""

from pathlib import Path

from meridian.lib.harness.registry import HarnessRegistry

from .command import (
    build_harness_command,
    build_launch_env,
    normalize_system_prompt_passthrough_args,
)
from .process import (
    ProcessOutcome,
    active_primary_lock_path,
    cleanup_orphaned_locks,
    run_harness_process,
)
from .plan import (
    ResolvedPrimaryLaunchPlan,
    resolve_primary_launch_plan,
)
from .resolve import (
    ResolvedSkills,
    load_agent_profile_with_fallback,
    resolve_harness,
    resolve_primary_session_metadata,
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
            lock_path=plan.lock_path,
            continue_ref=None,
        )

    outcome = run_harness_process(plan, harness_registry)
    continue_ref = outcome.resolved_harness_session_id.strip() or None

    return LaunchResult(
        command=outcome.command,
        exit_code=outcome.exit_code,
        lock_path=plan.lock_path,
        continue_ref=continue_ref,
    )


__all__ = [
    "LaunchRequest",
    "LaunchResult",
    "ResolvedPrimaryLaunchPlan",
    "PrimarySessionMetadata",
    "ProcessOutcome",
    "ResolvedSkills",
    "active_primary_lock_path",
    "build_harness_command",
    "build_launch_env",
    "build_primary_prompt",
    "cleanup_orphaned_locks",
    "launch_primary",
    "load_agent_profile_with_fallback",
    "normalize_system_prompt_passthrough_args",
    "resolve_harness",
    "resolve_primary_launch_plan",
    "resolve_primary_session_metadata",
    "resolve_skills_from_profile",
    "run_harness_process",
]
