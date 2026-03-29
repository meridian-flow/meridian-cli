"""Public launch API."""

from pathlib import Path

from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.ops.work_attachment import ensure_explicit_work_item

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


def _resolve_work_id_for_launch(state_root: Path, request: LaunchRequest) -> str | None:
    """Resolve work item before entering the launch layer (policy, not mechanism)."""

    explicit_work_id = (request.work_id or "").strip() or None
    if explicit_work_id is not None:
        return ensure_explicit_work_item(state_root, explicit_work_id)
    return None


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
            warning=plan.warning,
        )

    # Resolve work-item attachment at the policy layer, not inside the
    # process mechanism.  This keeps lib/launch free of ops dependencies.
    resolved_work_id = _resolve_work_id_for_launch(plan.state_root, request)
    resolved_plan = plan.model_copy(update={"resolved_work_id": resolved_work_id})

    outcome = run_harness_process(resolved_plan, harness_registry)
    continue_ref = outcome.resolved_harness_session_id.strip() or None

    return LaunchResult(
        command=outcome.command,
        exit_code=outcome.exit_code,
        continue_ref=continue_ref,
        warning=plan.warning,
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
