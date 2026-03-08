"""Public launch API."""

from pathlib import Path

from meridian.lib.harness.registry import HarnessRegistry

from .command import (
    PrimaryHarnessContext,
    build_harness_command,
    build_harness_context,
    build_launch_env,
    normalize_system_prompt_passthrough_args,
)
from .process import (
    LaunchContext,
    ProcessOutcome,
    active_primary_lock_path,
    cleanup_orphaned_locks,
    prepare_launch_context,
    run_harness_process,
)
from .resolve import (
    ResolvedSkills,
    load_agent_profile_with_fallback,
    resolve_harness,
    resolve_permission_tier_from_profile,
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

    ctx = prepare_launch_context(repo_root, request, harness_registry)

    if request.dry_run:
        command = build_harness_command(
            repo_root=repo_root,
            request=ctx.command_request,
            prompt=ctx.prompt,
            harness_registry=harness_registry,
            chat_id="dry-run",
            config=ctx.config,
        )
        return LaunchResult(
            command=command,
            exit_code=0,
            lock_path=ctx.lock_path,
            continue_ref=None,
        )

    outcome = run_harness_process(repo_root, request, ctx, harness_registry)
    continue_ref = outcome.resolved_harness_session_id.strip() or None

    return LaunchResult(
        command=outcome.command,
        exit_code=outcome.exit_code,
        lock_path=ctx.lock_path,
        continue_ref=continue_ref,
    )


__all__ = [
    "LaunchContext",
    "LaunchRequest",
    "LaunchResult",
    "PrimaryHarnessContext",
    "PrimarySessionMetadata",
    "ProcessOutcome",
    "ResolvedSkills",
    "active_primary_lock_path",
    "build_harness_command",
    "build_harness_context",
    "build_launch_env",
    "build_primary_prompt",
    "cleanup_orphaned_locks",
    "launch_primary",
    "load_agent_profile_with_fallback",
    "normalize_system_prompt_passthrough_args",
    "prepare_launch_context",
    "resolve_harness",
    "resolve_permission_tier_from_profile",
    "resolve_primary_session_metadata",
    "resolve_skills_from_profile",
    "run_harness_process",
]
