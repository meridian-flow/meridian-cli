"""Primary agent launcher facade over launch internals."""


from pathlib import Path

from meridian.lib.harness.registry import HarnessRegistry

# Re-export public API from submodules so existing imports keep working.
from meridian.lib.launch.command import (
    PrimaryHarnessContext as PrimaryHarnessContext,
    build_harness_command as build_harness_command,
    build_harness_context as build_harness_context,
    build_space_env as build_space_env,
    normalize_system_prompt_passthrough_args as normalize_system_prompt_passthrough_args,
)
from meridian.lib.launch.process import (
    LaunchContext as LaunchContext,
    ProcessOutcome as ProcessOutcome,
    cleanup_orphaned_locks as cleanup_orphaned_locks,
    prepare_launch_context,
    run_harness_process,
    space_lock_path as space_lock_path,
)
from meridian.lib.launch.resolve import (
    resolve_harness as resolve_harness,
    resolve_primary_session_metadata as resolve_primary_session_metadata,
)
from meridian.lib.launch.types import (
    PrimarySessionMetadata as PrimarySessionMetadata,
    SpaceLaunchRequest as SpaceLaunchRequest,
    SpaceLaunchResult as SpaceLaunchResult,
    build_primary_prompt as build_primary_prompt,
)


def launch_primary(
    *,
    repo_root: Path,
    request: SpaceLaunchRequest,
    harness_registry: HarnessRegistry,
) -> SpaceLaunchResult:
    """Launch primary agent process and wait for exit."""

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
        return SpaceLaunchResult(
            command=command,
            exit_code=0,
            lock_path=ctx.lock_path,
            continue_ref=None,
        )

    outcome = run_harness_process(repo_root, request, ctx, harness_registry)
    continue_ref = outcome.resolved_harness_session_id.strip() or None

    return SpaceLaunchResult(
        command=outcome.command,
        exit_code=outcome.exit_code,
        lock_path=ctx.lock_path,
        continue_ref=continue_ref,
    )
